"""entry.py — the single command surface.

Stage 1 implements `plan` and `selfcheck` (no model calls). `dummy`, `run` and
`analyze` are wired in later stages; they fail loudly rather than doing something
half-built.

    python3 -m harness2.entry plan
    python3 -m harness2.entry plan --config harness2/experiment.json --out runs/plan.json
    python3 -m harness2.entry selfcheck
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness2.config import (Config, ConfigError, PlanMismatch, load_config,  # type: ignore
                                 seats)
else:
    from .config import Config, ConfigError, PlanMismatch, load_config, seats

DEFAULT_CONFIG = Path(__file__).with_name("experiment.json")


def _print_plan(config: Config, plan: dict, path: Path) -> None:
    counts = plan["counts"]
    print(f"config:        {config.path}")
    print(f"model:         {config.model_name} ({config.model_provider}, think={config.think})")
    print(f"total cells:   {plan['total_cells']}")
    print("per scenario:  " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"call range:    {plan['calls_min']:,} .. {plan['calls_max']:,} (one model call per seat-turn)")
    print(f"config hash:   {plan['config_hash']}")
    print(f"schedule hash: {plan['schedule_hash']}")
    print(f"plan written:  {path}")
    print()
    print("first cells (schedule order):")
    for cell in plan["cells"][:8]:
        print(f"  {cell['cell_id']:<28} seats={''.join(cell['seats'])}")
    if len(plan["cells"]) > 8:
        print(f"  ... {len(plan['cells']) - 8} more")
    if config.model_name.upper() == "TBD":
        print()
        print("NOTE: model.name is TBD. `run` will refuse until the cheapest")
        print("      tool-capable Ollama model is selected and recorded.")


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate(for_run=False)
    out = Path(args.out) if args.out else config.runs_dir / "plan.json"
    plan = config.write_plan(out)
    _print_plan(config, plan, out)
    print()
    print("No model calls were made.")
    return 0


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def cmd_selfcheck(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate(for_run=False)

    cells = config.cells()
    schedule = config.schedule()

    # Structural invariants. These are config-level checks; scenario anchors and
    # the engine/recorder contract are exercised in later stage selfchecks.
    _check(len({c.cell_id for c in cells}) == len(cells), "duplicate cell ids")
    _check(len(schedule) == len(cells), "schedule is not a permutation of cells")
    _check({c.cell_id for c in schedule} == {c.cell_id for c in cells},
           "schedule lost or invented a cell")
    _check(all(len(c.seats) == c.n for c in cells), "seat labels do not match N")
    _check(all(c.n == 3 for c in cells if c.scenario == "s4"), "S4 must be N=3")
    _check(all(c.rung == 0 for c in cells if c.n == 1), "N=1 must run rung 0 only")
    _check(config.schedule_hash() == config.schedule_hash(), "schedule hash is unstable")
    _check(config.config_hash() == config.config_hash(), "config hash is unstable")
    _check(config.comms.get("topology") == "forum_dm",
           f"unsupported comms topology: {config.comms.get('topology')!r}")

    counts = config.counts()
    expected = {"s1": 90, "s2": 90, "s3": 90, "s4": 40}
    if counts == expected:
        print("default matrix: 310 cells (S1=90, S2=90, S3=90, S4=40)")
    else:
        print(f"non-default matrix: {len(cells)} cells {counts}")
        print("  (runtime-tunable configs are allowed; `run` still needs an approved plan)")

    print(f"seats:         N=1 -> {''.join(seats(1))}; "
          f"N=4 -> {''.join(seats(4))}; N=12 -> {''.join(seats(12))}")
    print(f"rungs:         {config.rungs}")
    print(f"seeds:         {len(config.seeds)} fixed")
    print(f"turns:         cap {config.max_turns} per agent per cycle")
    print(f"config hash:   {config.config_hash()}")
    print(f"schedule hash: {config.schedule_hash()}")
    print("config selfcheck: OK")
    print("No model calls were made.")
    return 0


def cmd_not_implemented(args: argparse.Namespace) -> int:
    stage = {
        "dummy": "stage 4 (engine/recorder) / stage 5 (S1)",
        "run": "stage 11 (walk test) or stage 13 (matrix, with approval)",
        "analyze": "stage 6 (analysis)",
    }.get(args.command, "a later stage")
    print(f"`{args.command}` is not wired yet; it lands in {stage}.", file=sys.stderr)
    print("Nothing was run and no model calls were made.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness2.entry",
        description="Bitrate × collusion harness: plan, selfcheck, dummy, run, analyze.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_config(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help=f"experiment config (default: {DEFAULT_CONFIG})")

    plan = sub.add_parser("plan", help="resolve the cell schedule and write plan.json")
    add_config(plan)
    plan.add_argument("--out", default=None, help="plan path (default: <runs>/plan.json)")
    plan.set_defaults(func=cmd_plan)

    selfcheck = sub.add_parser("selfcheck", help="config/schedule checks; no model calls")
    add_config(selfcheck)
    selfcheck.set_defaults(func=cmd_selfcheck)

    dummy = sub.add_parser("dummy", help="scripted end-to-end run; no model calls")
    add_config(dummy)
    dummy.add_argument("--scenario", default=None)
    dummy.add_argument("--limit", type=int, default=None)
    dummy.set_defaults(func=cmd_not_implemented)

    run = sub.add_parser("run", help="live model run; requires an approved plan")
    add_config(run)
    run.add_argument("--approve", required=True, help="plan.json generated by `plan`")
    run.add_argument("--scenario", default=None)
    run.add_argument("--limit", type=int, default=None)
    run.set_defaults(func=cmd_not_implemented)

    analyze = sub.add_parser("analyze", help="analysis over a finished run tree")
    analyze.add_argument("--runs", required=True)
    analyze.set_defaults(func=cmd_not_implemented)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, PlanMismatch) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
