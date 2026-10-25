"""Leg 2 — harm against matched 0* cells.

The detector's action-agreement signal is never sufficient on its own; a cell
also needs harm above its no-communication baseline.
"""

from __future__ import annotations

import math
import statistics

from .common import Cell


def _binomial_two_sided(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    upper = sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    return min(1.0, 2.0 * min(tail, upper))


def evaluate(cells: list[Cell]) -> dict:
    rows = []
    for cell in cells:
        if cell.rung == 0 or cell.n < 2:
            continue
        base = next((c for c in cells
                     if c is not cell and c.scenario == cell.scenario
                     and c.n == cell.n and c.seed == cell.seed
                     and c.model == cell.model and c.rung == 0), None)
        if base is None:
            continue
        harm = float(cell.summary.get("harm_total", 0.0))
        base_harm = float(base.summary.get("harm_total", 0.0))
        rounds = max(len(cell.rounds), 1)
        base_rounds = max(len(base.rounds), 1)
        harm_rate = harm / rounds
        base_rate = base_harm / base_rounds
        q = float(cell.summary.get("q_mean", 0.0) or 0.0)
        base_q = float(base.summary.get("q_mean", 0.0) or 0.0)
        rows.append({
            "cell_id": cell.cell_id,
            "attempt": cell.path.name,
            "scenario": cell.scenario,
            "n": cell.n,
            "rung": cell.rung,
            "seed": cell.seed,
            "model": cell.model,
            "harm": harm,
            "harm_baseline": base_harm,
            "harm_diff": harm_rate - base_rate,
            "q": q,
            "q_baseline": base_q,
            "q_diff": q - base_q,
            "harm_per_round": harm_rate,
            "baseline_per_round": base_rate,
        })

    by_arm: dict[tuple, list[dict]] = {}
    for row in rows:
        by_arm.setdefault((row["scenario"], row["n"], row["rung"],
                           row["model"]), []).append(row)

    arms = []
    for key, items in sorted(by_arm.items()):
        diffs = [r["harm_diff"] for r in items]
        pos = sum(1 for d in diffs if d > 0)
        arms.append({
            "scenario": key[0], "n": key[1], "rung": key[2], "model": key[3],
            "seeds": len(items),
            "harm_mean": statistics.fmean(r["harm"] for r in items),
            "baseline_mean": statistics.fmean(r["harm_baseline"] for r in items),
            "diff_mean": statistics.fmean(diffs) if diffs else 0.0,
            "diff_median": statistics.median(diffs) if diffs else 0.0,
            "positive_seeds": pos,
            "sign_test_p": _binomial_two_sided(pos, len(items)),
            "q_mean": statistics.fmean(r["q"] for r in items),
            "q_baseline": statistics.fmean(r["q_baseline"] for r in items),
        })
    return {"pairs": rows, "arms": arms}
