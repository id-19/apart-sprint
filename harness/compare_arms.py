"""compare_arms.py — read any task's cells back out of the registry and compare the arms.

    python3 harness/compare_arms.py --task plotA --markets 4
    python3 harness/compare_arms.py --task seed_v0b --markets 1

Reports, per arm: mean total, seed spread, mean harm, and where each cell sits against the correct
null (random day choice), because that null — not the all-crowd anchor — is what decides whether an
arm shows coordination at all.
"""
from __future__ import annotations
import argparse, json, random, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from registry import load_cells, PROJ   # noqa: E402


def random_null(seats, days, markets, n=100_000, seed=11):
    """Cost when nobody coordinates: each seat lands on a uniformly random day, per market."""
    rng = random.Random(seed)
    xs = []
    for _ in range(n):
        total = 0
        for _ in range(markets):
            c = [0] * days
            for _ in range(seats):
                c[rng.randrange(days)] += 1
            total += 20 * sum(x * x for x in c)
        xs.append(total)
    xs.sort()
    return xs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--seats", type=int, default=5)
    p.add_argument("--days", type=int, default=6)
    p.add_argument("--markets", type=int, default=1)
    a = p.parse_args()

    cells = load_cells(task=a.task, valid_only=True)
    if not cells:
        print(f"no valid cells for task {a.task!r} — run harness/registry.py first")
        return
    xs = random_null(a.seats, a.days, a.markets)
    p50, p5, p95 = xs[len(xs) // 2], xs[int(.05 * len(xs))], xs[int(.95 * len(xs))]
    mean = statistics.fmean(xs)
    print(f"task {a.task}: {len(cells)} cells · {a.markets} market(s) · random null "
          f"mean {mean:.1f}, median {p50:.0f}, 5-95th {p5:.0f}-{p95:.0f}\n")

    by_arm = {}
    for c in cells:
        by_arm.setdefault(c["arm"], []).append(c)

    print(f"{'arm':8s} {'n':>2s} {'mean':>8s} {'spread':>16s} {'harm':>7s}  cells (pct of random null)")
    for arm, cs in sorted(by_arm.items()):
        ts = [c["total_cost"] for c in cs]
        hs = [c.get("harm_concentration") or 0 for c in cs]
        pcts = [100 * sum(1 for x in xs if x <= t) / len(xs) for t in ts]
        spread = f"{min(ts)}-{max(ts)}" if len(ts) > 1 else f"{ts[0]}"
        print(f"{arm:8s} {len(cs):2d} {statistics.fmean(ts):8.1f} {spread:>16s} "
              f"{statistics.fmean(hs):7.1f}  {[round(p, 1) for p in pcts]}")

    if len(by_arm) == 2 and all(len(v) > 0 for v in by_arm.values()):
        f = statistics.fmean([c["total_cost"] for c in by_arm["free"]])
        s = statistics.fmean([c["total_cost"] for c in by_arm["silent"]])
        pooled = statistics.pstdev([c["total_cost"] for c in cells])
        print(f"\nfree {f:.1f} vs silent {s:.1f}: difference {f - s:+.1f} "
              f"({abs(f - s) / s * 100:.0f}% of silent), pooled sd across all cells {pooled:.1f}")
        print("a difference smaller than the pooled sd is not distinguishable at this n")
    if mean:
        for arm, cs in sorted(by_arm.items()):
            ts = [c["total_cost"] for c in cs]
            print(f"{arm}: mean is {(statistics.fmean(ts) / mean - 1) * 100:+.0f}% vs random null")


if __name__ == "__main__":
    main()
