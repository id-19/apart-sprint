"""entry.py — the single command surface.

    python3 -m harness2.entry plan
    python3 -m harness2.entry selfcheck
    python3 -m harness2.entry dummy --scenario s1 --limit 2
    python3 -m harness2.entry run --approve runs/plan.json --scenario s1 --limit 1
    python3 -m harness2.entry analyze --runs runs
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .config import (Config, ConfigError, CellSpec, PlanMismatch,
                     allocate_run_dir, load_config, seats)
from .engine import Engine
from .model import ModelClient
from .record import Recorder, append_manifest
from .realism import MetaFlagError
from .scenario import load_scenario
from .scripted import transport_for

DEFAULT_CONFIG = Path(__file__).with_name("experiment.json")


def _cell_from_dict(d: dict) -> CellSpec:
    return CellSpec(scenario=d["scenario"], rung=int(d["rung"]), n=int(d["n"]),
                    seed=int(d["seed"]), seats=tuple(d["seats"]))


def _num_ctx(cell: CellSpec) -> int:
    if cell.n >= 12:
        return 65536
    if cell.n >= 4 and cell.rung >= 8192:
        return 32768
    return 16384


def _fmt(value: float) -> str:
    return f"{value:.0f}" if abs(value) >= 10 or value == 0 else f"{value:.3f}"


# ---------------------------------------------------------------------------
# plan / selfcheck
# ---------------------------------------------------------------------------

def _print_plan(config: Config, plan: dict, path: Path) -> None:
    counts = plan["counts"]
    print(f"config:        {config.path}")
    print(f"model:         {config.model_name} ({config.model_provider}, think={config.think})")
    print(f"total cells:   {plan['total_cells']}")
    print("per scenario:  " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"call range:    {plan['calls_min']:,} .. {plan['calls_max']:,} (one model call per seat-exchange)")
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
        print("NOTE: model.name is TBD. `run` will refuse until a model is recorded.")


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate(for_run=False)
    out = Path(args.out) if args.out else config.runs_dir / "plan.json"
    plan = config.write_plan(out)
    _print_plan(config, plan, out)
    print("\nNo model calls were made.")
    return 0


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def cmd_selfcheck(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate(for_run=False)
    cells = config.cells()
    schedule = config.schedule()
    _check(len({c.cell_id for c in cells}) == len(cells), "duplicate cell ids")
    _check(len(schedule) == len(cells), "schedule is not a permutation of cells")
    _check({c.cell_id for c in schedule} == {c.cell_id for c in cells},
           "schedule lost or invented a cell")
    _check(all(len(c.seats) == c.n for c in cells), "seat labels do not match N")
    _check(all(c.n == 3 for c in cells if c.scenario == "s4"), "S4 must be N=3")
    _check(all(c.rung == 0 for c in cells if c.n == 1), "N=1 must run rung 0 only")
    _check(config.comms.get("topology") == "forum_dm",
           f"unsupported comms topology: {config.comms.get('topology')!r}")

    print(f"matrix: {len(cells)} cells {config.counts()}")
    print(f"seats:  N=1 -> {''.join(seats(1))}; N=4 -> {''.join(seats(4))}; "
          f"N=12 -> {''.join(seats(12))}")
    print(f"rungs:  {config.rungs}")
    print(f"config hash:   {config.config_hash()}")
    print(f"schedule hash: {config.schedule_hash()}")

    for name in config.scenarios:
        scenario = load_scenario(name)
        cell = CellSpec(name, 2048, scenario.default_seats, 0,
                        seats(scenario.default_seats))
        anchors = scenario.anchors(list(cell.seats), 0)
        with tempfile.TemporaryDirectory(prefix=f"selfcheck_{name}_") as td:
            results = {}
            for key in ("cartel", "honest", "independent", "failing"):
                if key not in anchors:
                    continue
                results[key] = _scripted_cell(scenario, cell, td, key, anchors[key])
            if "cartel" in results:
                _check(results["cartel"]["harm_total"] > 0,
                       f"{name}: cartel anchor produced no harm")
            if "honest" in results:
                _check(results["honest"]["harm_total"] == 0,
                       f"{name}: honest anchor produced harm")
            if "failing" in results:
                _check(results["failing"]["compliance"] < 0.75,
                       f"{name}: failing anchor passed compliance")
        print(f"scenario {name}: anchors OK "
              + ", ".join(f"{k}={_fmt(v['harm_total'])}" for k, v in results.items()))
    print("selfcheck: OK (no model calls)")
    return 0


def _scripted_cell(scenario, cell: CellSpec, root: str | Path, anchor: str,
                   policy) -> dict:
    run_dir = allocate_run_dir(Path(root), f"{cell.cell_id}_{anchor}")
    rec = Recorder(run_dir, {**cell.as_dict(), "anchor": anchor})
    client = ModelClient(run_dir=run_dir, cell_id=cell.cell_id, model="scripted",
                         think=False, transport=transport_for(policy))
    engine = Engine(cell=cell, scenario=scenario, cell_dir=run_dir,
                    client=client, recorder=rec, max_exchanges=6,
                    num_ctx=16384)
    return engine.run()


# ---------------------------------------------------------------------------
# dummy / run
# ---------------------------------------------------------------------------

def _select_cells(config: Config, scenario: str | None, limit: int | None,
                  cell_id: str | None = None) -> list[CellSpec]:
    cells = [c for c in config.schedule()
             if (scenario is None or c.scenario == scenario)
             and (cell_id is None or c.cell_id == cell_id)]
    if limit is not None:
        cells = cells[:max(0, limit)]
    return cells


def cmd_dummy(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate(for_run=False)
    cells = _select_cells(config, args.scenario, args.limit, args.cell)
    if not cells:
        print("No cells selected.", file=sys.stderr)
        return 1
    root = config.runs_dir / "dummy"
    root.mkdir(parents=True, exist_ok=True)
    for i, cell in enumerate(cells, 1):
        scenario = load_scenario(cell.scenario)
        anchors = scenario.anchors(list(cell.seats), cell.seed)
        if args.anchor not in anchors:
            print(f"{cell.scenario} has no {args.anchor!r} anchor", file=sys.stderr)
            return 1
        policy = anchors[args.anchor]
        run_dir = allocate_run_dir(root, cell.cell_id)
        rec = Recorder(run_dir, {**cell.as_dict(), "anchor": args.anchor})
        client = ModelClient(run_dir=run_dir, cell_id=cell.cell_id,
                             model="scripted", think=False,
                             transport=transport_for(policy))
        engine = Engine(cell=cell, scenario=scenario, cell_dir=run_dir,
                        client=client, recorder=rec, max_exchanges=6,
                        num_ctx=16384, cycles=args.cycles)
        try:
            summary = engine.run()
        except MetaFlagError as exc:
            print(f"STOP {cell.cell_id}: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # preserve partial data, then stop
            print(f"ERROR {cell.cell_id}: {exc}", file=sys.stderr)
            return 3
        print(f"[{i}/{len(cells)}] {cell.cell_id} harm={_fmt(summary['harm_total'])} "
              f"q={summary['q_mean']:.2f} compliance={summary['compliance']:.2f} "
              f"flags={len(summary['flags'])}")
    print(f"\nscripted cells written under {root}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate(for_run=True)
    plan = config.verify_plan(Path(args.approve))
    cells = [_cell_from_dict(c) for c in plan["cells"]
             if (args.scenario is None or c["scenario"] == args.scenario)
             and (args.cell is None or c["cell_id"] == args.cell)]
    if not args.all:
        cells = cells[:max(0, args.limit)]
    if not cells:
        print("No cells selected.", file=sys.stderr)
        return 1
    manifest = config.runs_dir / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    for i, cell in enumerate(cells, 1):
        scenario = load_scenario(cell.scenario)
        run_dir = allocate_run_dir(config.runs_dir, cell.cell_id)
        rec = Recorder(run_dir, cell.as_dict())
        client = ModelClient(run_dir=run_dir, cell_id=cell.cell_id,
                             model=config.model_name,
                             provider=config.model_provider,
                             think=config.think,
                             temperature=config.temperature,
                             num_ctx=_num_ctx(cell), seed=cell.seed)
        engine = Engine(cell=cell, scenario=scenario, cell_dir=run_dir,
                        client=client, recorder=rec,
                        max_exchanges=config.max_turns, num_ctx=_num_ctx(cell),
                        cycles=args.cycles)
        print(f"[{i}/{len(cells)}] {cell.cell_id} -> {run_dir}")
        try:
            summary = engine.run()
        except MetaFlagError as exc:
            append_manifest(manifest, {"cell_id": cell.cell_id, "status": "META_STOP",
                                       "detail": str(exc)})
            print(f"STOP {cell.cell_id}: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # preserve partial data, then stop
            append_manifest(manifest, {"cell_id": cell.cell_id, "status": "ERROR",
                                       "detail": str(exc)})
            print(f"ERROR {cell.cell_id}: {exc}", file=sys.stderr)
            return 3
        append_manifest(manifest, {"cell_id": cell.cell_id, "status": "DONE",
                                   "harm_total": summary["harm_total"],
                                   "q_mean": summary["q_mean"],
                                   "compliance": summary["compliance"]})
        print(f"    harm={_fmt(summary['harm_total'])} q={summary['q_mean']:.2f} "
              f"compliance={summary['compliance']:.2f} flags={len(summary['flags'])}")
    print(f"\n{len(cells)} cell(s) run; manifest at {manifest}")
    return 0


# ---------------------------------------------------------------------------
# analyze (lightweight; the full detector lives in analysis/)
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> int:
    root = Path(args.runs)
    rows = []
    for path in sorted(root.rglob("summary.json")):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "cell_id" not in s:
            continue
        rows.append(s)
    if not rows:
        print(f"No summaries under {root}", file=sys.stderr)
        return 1
    rows.sort(key=lambda s: (s.get("scenario"), s.get("n"), s.get("rung"), s.get("seed")))
    print(f"{'cell':<28} {'n':>2} {'rung':>6} {'harm':>8} {'q':>5} {'comp':>5} flags")
    for s in rows:
        print(f"{s['cell_id']:<28} {s['n']:>2} {s['rung']:>6} "
              f"{_fmt(s['harm_total']):>8} {s['q_mean']:>5.2f} "
              f"{s['compliance']:>5.2f} {len(s.get('flags', []))}")
    print(f"\n{len(rows)} cells")
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness2.entry",
        description="Bitrate x collusion harness: plan, selfcheck, dummy, run, analyze.")
    sub = p.add_subparsers(dest="command", required=True)

    def add_config(sp):
        sp.add_argument("--config", default=str(DEFAULT_CONFIG))

    plan = sub.add_parser("plan", help="resolve the cell schedule and write plan.json")
    add_config(plan)
    plan.add_argument("--out", default=None)
    plan.set_defaults(func=cmd_plan)

    check = sub.add_parser("selfcheck", help="config and scripted anchor checks")
    add_config(check)
    check.set_defaults(func=cmd_selfcheck)

    dummy = sub.add_parser("dummy", help="scripted end-to-end cells; no model calls")
    add_config(dummy)
    dummy.add_argument("--scenario", default=None)
    dummy.add_argument("--cell", default=None)
    dummy.add_argument("--limit", type=int, default=None)
    dummy.add_argument("--cycles", type=int, default=None)
    dummy.add_argument("--anchor", default="cartel",
                       choices=["cartel", "honest", "independent", "failing"])
    dummy.set_defaults(func=cmd_dummy)

    run = sub.add_parser("run", help="live model run; requires an approved plan")
    add_config(run)
    run.add_argument("--approve", required=True)
    run.add_argument("--scenario", default=None)
    run.add_argument("--cell", default=None)
    run.add_argument("--limit", type=int, default=1,
                     help="number of cells (default 1; use --all for the full selection)")
    run.add_argument("--all", action="store_true")
    run.add_argument("--cycles", type=int, default=None)
    run.set_defaults(func=cmd_run)

    analyze = sub.add_parser("analyze", help="lightweight summary over a run tree")
    analyze.add_argument("--runs", required=True)
    analyze.set_defaults(func=cmd_analyze)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, PlanMismatch, MetaFlagError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
