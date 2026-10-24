"""run_task.py — run any finalised task through the same free-vs-silent comparison.

    python3 harness/run_task.py --task plotA --model qwen3.5:2b --bits 10000000 \
        --seeds 3 --tag free --out runs/plotA_v0

The point of this file is that the arm is the only thing that changes between calls: same task, same
seeds, same parameters, same engine. Any difference in outcome is attributable to the channel.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from seed_collusion import run            # noqa: E402
from tasks import flow_plotA, flow_seed   # noqa: E402

TASKS = {
    "seed": flow_seed,    # T0: one market, equal deadlines
    "plotA": flow_plotA,  # finalised Plot A: 4 markets, common release, staggered deadlines
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", default="plotA", choices=sorted(TASKS))
    p.add_argument("--model", default="qwen3.5:2b")
    p.add_argument("--bits", type=int, default=10_000_000)
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--tag", default="free")
    p.add_argument("--out", required=True)
    p.add_argument("--seats", type=int, default=5)
    p.add_argument("--days", type=int, default=6)
    p.add_argument("--lots", type=int, default=5)
    p.add_argument("--impact-lots", type=int, default=50)
    p.add_argument("--sigma", type=float, default=0.0015)
    p.add_argument("--force", action="store_true")
    a = p.parse_args()

    out_root = Path(a.out)
    flow = TASKS[a.task](a.seats, a.days, a.lots)
    for seed in range(1, a.seeds + 1):
        cell = out_root / f"{a.tag}-s{seed}"
        if cell.exists() and not a.force:
            print(f"=== {a.task} {a.tag} seed {seed}: exists, skipping ({cell}) ===")
            continue
        print(f"=== {a.task} {a.tag} seed {seed} -> {cell} ===", flush=True)
        run(a.model, a.bits, a.seats, a.days, seed, a.lots, a.impact_lots, a.sigma, cell,
            flow=flow, label=a.task)
        s = json.loads((cell / "summary.json").read_text())
        print(f"  total {s['total_cost']} per-seat {s['per_seat_cost']} days {s['days_used']} "
              f"harm {s.get('harm_concentration')} bits {s['admitted_bits']} "
              f"malformed {s['malformed']}", flush=True)


if __name__ == "__main__":
    main()
