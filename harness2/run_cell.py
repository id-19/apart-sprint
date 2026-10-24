"""run_cell.py — the cell driver. Owns gates → recorder → engine → summary.

Usage:
  python3 harness2/run_cell.py --model granite4.2:3b --rung 1024 --topology common \
      --seats A B C --seed 0 --rounds 8
Dry-run (no Ollama; scripted anchor) is what the engine's own tests already exercise.

Gates run before any LLM token is spent; a failed gate stops the cell and records it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import CellSpec, Engine, scripted_cartel, scripted_honest  # noqa: E402
from record import RunRecorder  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one S1 cell through gates then engine.")
    p.add_argument("--model", default="granite4.2:3b")
    p.add_argument("--rung", type=int, default=1024,
                   help="nominal bits: 0 | 512 | 1024 | 16384")
    p.add_argument("--topology", default="common", choices=["common", "mesh"])
    p.add_argument("--seats", nargs="+", default=["A", "B", "C"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--rounds", type=int, default=8)
    p.add_argument("--family", default="same-lineage")
    p.add_argument("--runs-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "runs"))
    return p


def main() -> int:
    args = build_parser().parse_args()
    spec = CellSpec(rung_bits=args.rung, topology=args.topology,
                    seats=list(args.seats), family=args.family,
                    seed=args.seed, rounds=args.rounds)
    run_dir = os.path.join(args.runs_root, spec.cell_id)
    os.makedirs(run_dir, exist_ok=True)

    # gates first — use scripted transports so no LLM call is spent on validation
    gate_engine = Engine(spec, os.path.join(run_dir, "_gates"), scripted_honest())
    gates = gate_engine.run_gates()
    if not gates.all_passed:
        print(f"GATE FAIL {spec.cell_id}: {gates}", file=sys.stderr)
        return 2

    # real cell: LLM transport is the Ollama HTTP default inside OllamaClient
    engine = Engine(spec, run_dir, transport=None, model=args.model)
    engine.gates = gates
    rec = RunRecorder(run_dir, spec.__dict__, gates.__dict__)
    engine.recorder = rec
    engine.run()
    total = sum(engine.compliance_counts.values())
    legal = engine.compliance_counts.get("legal", 0)
    rec.finalise({
        "harm_total": sum(r["harm"] for r in engine.world.rounds),
        "harm_rounds": sum(1 for r in engine.world.rounds if r["harm"] > 0),
        "extraction_total": sum(r["extraction"] for r in engine.world.rounds),
        "dead_or_malformed": engine.compliance_counts.get("malformed", 0),
        "infra": engine.compliance_counts.get("infra", 0),
        "compliance": legal / max(total, 1),
        "peak_rss_mb": rec._peaks.get("rss_mb", 0.0),
    })
    with open(os.path.join(run_dir, "summary.json")) as f:
        print(json.dumps(json.load(f), indent=2))
    print(f"\nrecords → {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
