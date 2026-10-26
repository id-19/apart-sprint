"""The floor question: does collusion appear at the lowest allowance?

    python3 -m analysis.floor --runs runs

Per model and scenario, reports each rung's mean harm and mean pairwise
agreement, then a monotone trend of harm on the rung (Spearman rho with a
permutation p-value).  Rung 0 is the no-channel control and enters the trend as
zero characters; it is never described as a zero bitrate.

Also prints, for each treated cell, the excess agreement over its matched
no-channel cell (same model, scenario, seat count and seed) — Leg 1's raw
quantity.
"""

from __future__ import annotations

import argparse
import random
import statistics
from collections import defaultdict
from pathlib import Path

from .common import load_cells


def _mean(values):
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None

    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        out = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = rank
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = _mean(rx), _mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def permutation_p(xs: list[float], ys: list[float], rho: float,
                  n: int = 5000, seed: int = 0) -> float | None:
    if rho is None:
        return None
    rng = random.Random(seed)
    ys = list(ys)
    hits = 0
    for _ in range(n):
        rng.shuffle(ys)
        r = spearman(xs, ys)
        if r is not None and abs(r) >= abs(rho) - 1e-12:
            hits += 1
    return (hits + 1) / (n + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis.floor")
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--permutations", type=int, default=5000)
    args = parser.parse_args(argv)

    cells = load_cells(args.runs, include_scripted=False)
    if not cells:
        print("no cells for the recorded design")
        return 1

    groups: dict[tuple, list] = defaultdict(list)
    for cell in cells:
        groups[(cell.model, cell.scenario, cell.rung)].append(cell)
    scenarios = sorted({k[1] for k in groups})
    models = sorted({k[0] for k in groups})

    print("| model | scenario | rung | cells | harm mean | sd | agreement | messages |")
    print("|---|---|---|---|---|---|---|---|")
    for model in models:
        for scenario in scenarios:
            rungs = sorted(k[2] for k in groups if k[0] == model and k[1] == scenario)
            for rung in rungs:
                group = groups[(model, scenario, rung)]
                harms = [c.summary.get("harm_total", 0.0) for c in group]
                rounds = [r for c in group for r in c.rounds]
                sd = statistics.stdev(harms) if len(harms) > 1 else None
                label = "no channel" if rung == 0 else str(rung)
                print(f"| {model} | {scenario} | {label} | {len(group)} "
                      f"| {_mean(harms):,.0f} | "
                      f"{f'{sd:,.0f}' if sd is not None else '-'} "
                      f"| {_mean([r.get('agreement') for r in rounds]) or 0:.2f} "
                      f"| {_mean([r.get('messages') for r in rounds]) or 0:.1f} |")

    print("\n### Trend of harm on the allowance")
    print("| model | scenario | cells | spearman rho | permutation p | reads as |")
    print("|---|---|---|---|---|---|")
    for model in models:
        for scenario in scenarios:
            group = [c for c in cells if c.model == model and c.scenario == scenario]
            if len({c.rung for c in group}) < 3:
                continue
            xs = [float(c.rung) for c in group]
            ys = [float(c.summary.get("harm_total", 0.0)) for c in group]
            rho = spearman(xs, ys)
            p = permutation_p(xs, ys, rho, args.permutations)
            if rho is None:
                verdict = "not enough spread"
            elif p is not None and p < 0.05 and rho > 0:
                verdict = "rises with the allowance"
            elif p is not None and p < 0.05 and rho < 0:
                verdict = "falls with the allowance"
            else:
                verdict = "no monotone trend yet"
            print(f"| {model} | {scenario} | {len(group)} "
                  f"| {f'{rho:+.2f}' if rho is not None else '-'} "
                  f"| {f'{p:.3f}' if p is not None else '-'} | {verdict} |")

    baseline = {(c.model, c.scenario, c.n, c.seed): c
                for c in cells if c.rung == 0}
    print("\n### Leg 1 raw quantity: excess agreement over the matched no-channel cell")
    print("| cell | rung | agreement | baseline | excess |")
    print("|---|---|---|---|---|")
    for cell in sorted(cells, key=lambda c: (c.model, c.scenario, c.rung, c.seed)):
        if cell.rung == 0:
            continue
        base = baseline.get((cell.model, cell.scenario, cell.n, cell.seed))
        if base is None:
            continue
        a = _mean([r.get("agreement") for r in cell.rounds])
        b = _mean([r.get("agreement") for r in base.rounds])
        if a is None or b is None:
            continue
        print(f"| {cell.cell_id} | {cell.rung} | {a:.2f} | {b:.2f} | {a - b:+.2f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
