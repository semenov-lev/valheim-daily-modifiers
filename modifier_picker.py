#!/usr/bin/env python3
"""Выбирает сбалансированную комбинацию модификаторов Valheim.

Режимы:
  modifier_picker.py modifiers.json                 → JSON комбинации в stdout
  modifier_picker.py modifiers.json --stats 10000   → таблица распределения

Читает modifiers.json, делает взвешенный случайный выбор по пулу,
проверяет сумму difficulty score на попадание в диапазон,
при необходимости перебрасывает.
"""
import argparse
import json
import random
import sys
from itertools import product


# ─────────────────────────────────────────────────────────────────────
# Базовые примитивы
# ─────────────────────────────────────────────────────────────────────

def weighted_pick(weights: dict) -> str:
    """Выбирает ключ с учётом весов.

    ValueError, если сумма весов <= 0 — иначе random.choices
    ведёт себя неопределённо.
    """
    keys = list(weights.keys())
    vals = list(weights.values())
    if sum(vals) <= 0:
        raise ValueError(
            f"Сумма весов должна быть > 0, получено: {weights!r}"
        )
    return random.choices(keys, weights=vals, k=1)[0]


def difficulty(combo: dict, scores: dict) -> float:
    """Сумма difficulty score по всем модификаторам.

    Значения без явного score считаются нейтральными (0.0).
    """
    return sum(scores.get(mod, {}).get(val, 0.0) for mod, val in combo.items())


def pick_balanced(pool: dict, scores: dict, lo: float, hi: float,
                  max_attempts: int = 100) -> tuple[dict, float, int]:
    """Возвращает (combo, score, attempts).

    Делает до max_attempts взвешенных выборок; возвращает первую,
    чья сумма score попадает в [lo, hi]. Если ни одна не попала —
    возвращает fallback (всё 'normal'), score=0.0, attempts=max_attempts.
    """
    for attempt in range(1, max_attempts + 1):
        combo = {mod: weighted_pick(weights) for mod, weights in pool.items()}
        score = difficulty(combo, scores)
        if lo <= score <= hi:
            return combo, score, attempt
    combo = {mod: "normal" for mod in pool}
    return combo, 0.0, max_attempts


# ─────────────────────────────────────────────────────────────────────
# Валидация конфига (для deploy.sh)
# ─────────────────────────────────────────────────────────────────────

def can_value_fit(target_mod: str, target_val: str, pool: dict,
                  scores: dict, lo: float, hi: float) -> bool:
    """Существует ли комбинация, где target_mod=target_val и score в [lo, hi]."""
    other_mods = [m for m in pool if m != target_mod]
    other_choices = [list(pool[m].keys()) for m in other_mods]
    base = scores.get(target_mod, {}).get(target_val, 0.0)

    for combo in product(*other_choices):
        total = base + sum(
            scores.get(m, {}).get(v, 0.0) for m, v in zip(other_mods, combo)
        )
        if lo <= total <= hi:
            return True
    return False


def validate_config(config: dict) -> dict[str, list[str]]:
    """Возвращает {категория: [детали]}. Пустой dict = конфиг валиден.

    Категории:
      structure               — отсутствуют обязательные поля или они некорректны
      empty_pool              — пустой pool у модификатора
      zero_total_weight       — сумма весов у модификатора <= 0
      zero_weight_values      — значения с весом <= 0 (никогда не выберутся)
      missing_scores          — значения пула без score
      unreachable             — значения, не помещающиеся в difficulty_range
      no_normal_for_fallback  — нет 'normal' в пуле (fallback не сработает)
    """
    problems: dict[str, list[str]] = {}

    pool = config.get("pool", {})
    balance = config.get("balance", {})
    scores = balance.get("scores", {})
    rng = balance.get("difficulty_range")

    if not pool:
        problems.setdefault("structure", []).append("pool пуст или отсутствует")
    if not rng or len(rng) != 2 or rng[0] > rng[1]:
        problems.setdefault("structure", []).append(
            f"difficulty_range должен быть [lo, hi] с lo <= hi, получено: {rng}"
        )
        return problems

    lo, hi = rng

    for mod, weights in pool.items():
        if not weights:
            problems.setdefault("empty_pool", []).append(mod)
            continue
        if sum(weights.values()) <= 0:
            problems.setdefault("zero_total_weight", []).append(mod)
        zero_w = [v for v, w in weights.items() if w <= 0]
        if zero_w:
            problems.setdefault("zero_weight_values", []).append(
                f"{mod}: {sorted(zero_w)}"
            )
        if "normal" not in weights:
            problems.setdefault("no_normal_for_fallback", []).append(mod)

    for mod, weights in pool.items():
        missing = set(weights) - set(scores.get(mod, {}))
        if missing:
            problems.setdefault("missing_scores", []).append(
                f"{mod}: {sorted(missing)}"
            )

    unreachable = {}
    for mod, weights in pool.items():
        for val in weights:
            if not can_value_fit(mod, val, pool, scores, lo, hi):
                unreachable.setdefault(mod, []).append(val)
    if unreachable:
        problems["unreachable"] = [
            f"{k}: {sorted(v)}" for k, v in unreachable.items()
        ]

    return problems


# ─────────────────────────────────────────────────────────────────────
# Статистика (для настройки весов)
# ─────────────────────────────────────────────────────────────────────

def simulate(pool: dict, scores: dict, lo: float, hi: float,
             n: int = 10000, max_attempts: int = 100) -> dict:
    """Считает picked / accepted / rejection по всем значениям пула.

    picked    — сколько раз значение выбрал weighted_pick (на любой попытке)
    accepted  — сколько раз значение попало в принятую комбинацию (или fallback)
    rejection — доля пиков, чья комбинация была отброшена difficulty_range
    """
    picked = {mod: {v: 0 for v in w} for mod, w in pool.items()}
    accepted = {mod: {v: 0 for v in w} for mod, w in pool.items()}
    fallbacks = 0
    scores_hist: dict[float, int] = {}

    for _ in range(n):
        for attempt in range(1, max_attempts + 1):
            combo = {mod: weighted_pick(w) for mod, w in pool.items()}
            s = difficulty(combo, scores)
            ok = lo <= s <= hi
            for mod, val in combo.items():
                picked[mod][val] += 1
                if ok:
                    accepted[mod][val] += 1
            if ok:
                scores_hist[round(s, 2)] = scores_hist.get(round(s, 2), 0) + 1
                break
        else:
            fallbacks += 1
            for mod in pool:
                accepted[mod]["normal"] += 1
            scores_hist[0.0] = scores_hist.get(0.0, 0) + 1

    per_mod = {}
    for mod, values in picked.items():
        total_picked = sum(values.values())
        per_mod[mod] = {}
        for val in values:
            p = picked[mod][val]
            a = accepted[mod][val]
            per_mod[mod][val] = {
                "picked": p,
                "accepted": a,
                "picked_pct": 100 * p / total_picked if total_picked else 0,
                "accepted_pct": 100 * a / n,
                "rejection_pct": 100 * (p - a) / p if p else 0,
            }

    return {
        "n": n,
        "fallbacks": fallbacks,
        "fallback_pct": 100 * fallbacks / n,
        "per_modifier": per_mod,
        "scores_hist": scores_hist,
    }


def format_stats(stats: dict) -> str:
    """Форматирует результат simulate() в читаемую таблицу."""
    lines = [f"Симуляция: {stats['n']} прогонов\n"]
    for mod, values in stats["per_modifier"].items():
        lines.append(f"── {mod} ──")
        lines.append(f"  {'value':<12} {'picked%':>8} {'accepted%':>10} {'rejected%':>10}")
        for val, d in values.items():
            lines.append(
                f"  {val:<12} {d['picked_pct']:>7.1f}% "
                f"{d['accepted_pct']:>9.1f}% {d['rejection_pct']:>9.1f}%"
            )
        lines.append("")

    lines.append(f"Fallback: {stats['fallback_pct']:.2f}% "
                 f"({stats['fallbacks']}/{stats['n']})")

    if stats["scores_hist"]:
        lines.append("\nDifficulty distribution:")
        for score in sorted(stats["scores_hist"]):
            cnt = stats["scores_hist"][score]
            pct = 100 * cnt / stats["n"]
            bar = "█" * max(1, int(pct / 2)) if pct > 0 else ""
            lines.append(f"  {score:+.2f}: {cnt:>5} ({pct:>5.1f}%) {bar}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────────────

def main(path: str, stats_n: int = 0) -> None:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    pool = cfg["pool"]
    balance = cfg.get("balance", {})
    scores = balance.get("scores", {})
    lo, hi = balance.get("difficulty_range", [-100, 100])
    max_attempts = balance.get("max_attempts", 100)

    if stats_n:
        stats = simulate(pool, scores, lo, hi, n=stats_n, max_attempts=max_attempts)
        print(format_stats(stats))
        return

    combo, score, attempts = pick_balanced(pool, scores, lo, hi, max_attempts)
    result = {
        **combo,
        "setkeys": cfg.get("setkeys", []),
        "_difficulty_score": round(score, 2),
        "_attempts": attempts,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Valheim modifier picker")
    p.add_argument("config", help="path to modifiers.json")
    p.add_argument("--stats", type=int, metavar="N", default=0,
                   help="показать распределение за N прогонов вместо одного выбора")
    args = p.parse_args()
    main(args.config, args.stats)