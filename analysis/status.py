"""Live progress board for the floor arms.

    python3 -m analysis.status --runs runs

Shows, per model and arm, how many cells are finished, the mean harm and the
mean pairwise agreement, how much was said, and how many flags fired.  Cells
still in flight (a run directory without a summary) are counted separately so
a worker that has stopped is visible as such.

Design-gated: cells from an earlier engine or scenario version are ignored, so
the board never mixes a stale run into today's numbers.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .common import load_cells


def _mean(values):
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def _fmt(value, digits=2):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def in_flight(root: Path, known: set[Path], recent_h: float = 6.0) -> list[dict]:
    """Run directories written recently that have a cell but no summary.

    Old abandoned attempts also have a ``cell.json`` and no summary; the age
    filter keeps them from looking like work in progress.
    """
    import time

    cutoff = time.time() - recent_h * 3600.0
    rows = []
    for cell_json in sorted(root.rglob("cell.json")):
        path = cell_json.parent
        if path in known or (path / "summary.json").exists():
            continue
        try:
            if cell_json.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        try:
            meta = json.loads(cell_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
            "cell_id": meta.get("cell_id", path.name),
            "scenario": meta.get("scenario", ""),
            "rung": meta.get("rung"),
            "seed": meta.get("seed"),
            "model": meta.get("model", ""),
            "cycles": sum(1 for _ in (path / "settlement.jsonl").open()
                          ) if (path / "settlement.jsonl").exists() else 0,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis.status")
    parser.add_argument("--runs", default="runs")
    args = parser.parse_args(argv)

    root = Path(args.runs)
    cells = load_cells(root, include_scripted=False)
    known = {c.path for c in cells}
    # Only the current ladder and the scenarios in the running arms: abandoned
    # attempts from an earlier config share the tree and must not look live.
    ladder = {0, 128, 512, 1024}
    flying = [r for r in in_flight(root, known)
              if r["scenario"] in ("s1", "s2", "s3", "s4") and r["rung"] in ladder]
    # Killed attempts leave their directory behind under the same cell id;
    # report the newest attempt at each cell, not every corpse.
    newest: dict[str, dict] = {}
    for row in flying:
        current = newest.get(row["cell_id"])
        if current is None or row["cycles"] > current["cycles"]:
            newest[row["cell_id"]] = row
    flying = sorted(newest.values(), key=lambda r: (r["model"], r["scenario"], r["rung"]))

    arms: dict[tuple, list] = defaultdict(list)
    for cell in cells:
        arms[(cell.model, cell.scenario, cell.rung)].append(cell)

    print(f"{len(cells)} finished, {len(flying)} in flight under {root}\n")
    print("| model | scenario | rung | cells | harm mean | agreement | msg/round | flags |")
    print("|---|---|---|---|---|---|---|---|")
    for key in sorted(arms):
        model, scenario, rung = key
        group = arms[key]
        rounds = [r for c in group for r in c.rounds]
        flags = sum(len(r.get("flags") or []) for r in rounds)
        print(f"| {model} | {scenario} | {rung if rung else 'no channel'} "
              f"| {len(group)} | {_fmt(_mean([c.summary.get('harm_total') for c in group]), 0)} "
              f"| {_fmt(_mean([r.get('agreement') for r in rounds]))} "
              f"| {_fmt(_mean([r.get('messages') for r in rounds]))} | {flags} |")

    if flying:
        print("\nIn flight:")
        for row in flying[:12]:
            print(f"- {row['cell_id']} ({row['model']}) cycle {row['cycles']}")
        if len(flying) > 12:
            print(f"- ... {len(flying) - 12} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
