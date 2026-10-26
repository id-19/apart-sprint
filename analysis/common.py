"""Loading and round-level summaries over the run tree.

A run directory is one cell attempt.  Nothing here mutates the tree.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

NON_ACTIONS = {"NONE", "WITHHOLD", "DECLINE", ""}


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    return rows


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@dataclass
class Cell:
    path: Path
    cell_id: str
    scenario: str
    rung: int
    n: int
    seed: int
    model: str
    summary: dict
    anchor: str = ""
    settlements: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    trajectories: list[dict] = field(default_factory=list)

    @property
    def scripted(self) -> bool:
        return self.model in ("scripted", "")

    @property
    def seats(self) -> list[str]:
        seats = self.summary.get("seats")
        if seats:
            return list(seats)
        bins = {}
        for row in self.settlements:
            bins.update(row.get("bins") or {})
        return sorted(bins)

    @property
    def key(self) -> tuple:
        return (self.scenario, self.n, self.rung, self.seed, self.model,
                self.anchor)

    @property
    def rounds(self) -> list[dict]:
        """Round-wise summary, one row per settled cycle."""
        by_cycle = {row.get("cycle"): row for row in self.settlements
                    if row.get("cycle") is not None}
        out = []
        for row in sorted(by_cycle.values(), key=lambda r: r.get("cycle", 0)):
            bins = row.get("bins") or {}
            verdicts = row.get("verdicts") or {}
            active = [s for s in bins
                      if verdicts.get(s) == "ACTION"
                      and str(bins.get(s, "")) not in NON_ACTIONS]
            agree = _agreement([bins[s] for s in active])
            agree_all = _agreement([bins[s] for s in bins
                                    if str(bins.get(s, "")) not in NON_ACTIONS])
            out.append({
                "cell_id": self.cell_id,
                "scenario": self.scenario,
                "rung": self.rung,
                "n": self.n,
                "seed": self.seed,
                "model": self.model,
                "anchor": self.anchor,
                "round": row.get("cycle", 0) + 1,
                "harm": float(row.get("harm", 0.0)),
                "q": _q(self, row),
                "messages": int(row.get("messages_admitted", 0) or 0),
                "bytes": int(row.get("admitted_bytes", 0) or 0),
                "rejected": int(row.get("messages_rejected", 0) or 0),
                "agreement": agree,
                "agreement_all": agree_all,
                "kappa": _kappa([bins[s] for s in active]),
                "active_seats": len(active),
                "uniform": bool(active and len(set(bins[s] for s in active)) == 1),
                "compliance": _compliance(bins, verdicts),
                "flags": _flag_kinds(row),
                "bins": {s: bins[s] for s in bins},
                "verdicts": dict(verdicts),
            })
        return out

    def round_series(self, field_name: str) -> list:
        return [r.get(field_name) for r in self.rounds]


def load_cells(root: str | Path, *, include_scripted: bool = True) -> list[Cell]:
    cells: list[Cell] = []
    # A run tree written for one design may hold attempts from earlier ones.
    # The harness records the design it planned for; a summary that disagrees
    # is not evidence for this one.  Absent the file, nothing is filtered.
    design = _read_json(Path(root) / "design.json")
    versions = design.get("scenario_versions") or {}
    engine_version = design.get("engine_version")
    for summary_path in sorted(Path(root).rglob("summary.json")):
        summary = _read_json(summary_path)
        cell_meta = _read_json(summary_path.parent / "cell.json")
        if not summary and not cell_meta:
            continue
        cell_id = summary.get("cell_id") or cell_meta.get("cell_id")
        if not cell_id:
            continue
        scenario = str(summary.get("scenario", cell_meta.get("scenario", "")))
        if versions:
            if summary.get("scenario_version") != versions.get(scenario):
                continue
            if engine_version and summary.get("engine_version") != engine_version:
                continue
        model = str(summary.get("model", cell_meta.get("model", "")))
        if not include_scripted and model == "scripted":
            continue
        # A halted cell is evidence, never a scored observation.  Keeping it
        # out of dedupe_latest stops a later meta stop from shadowing the last
        # clean attempt at the same cell.
        if summary.get("halted"):
            continue
        cells.append(Cell(
            path=summary_path.parent,
            cell_id=cell_id,
            scenario=str(summary.get("scenario", cell_meta.get("scenario", ""))),
            rung=int(summary.get("rung", cell_meta.get("rung", 0))),
            n=int(summary.get("n", cell_meta.get("n", 1))),
            seed=int(summary.get("seed", cell_meta.get("seed", 0))),
            model=model,
            summary=summary,
            anchor=str(cell_meta.get("anchor", summary.get("anchor", ""))),
            settlements=_read_jsonl(summary_path.parent / "settlement.jsonl"),
            messages=_read_jsonl(summary_path.parent / "messages.jsonl"),
            trajectories=_read_jsonl(summary_path.parent / "trajectory.jsonl"),
        ))
    return cells


def dedupe_latest(cells: list[Cell]) -> list[Cell]:
    """Keep the latest finished attempt for each (scenario, n, rung, seed, model)."""
    keep: dict[tuple, Cell] = {}
    for cell in cells:
        finished = float(cell.summary.get("finished_at", 0.0))
        old = keep.get(cell.key)
        if old is None or finished >= float(old.summary.get("finished_at", 0.0)):
            keep[cell.key] = cell
    return sorted(keep.values(), key=lambda c: (c.scenario, c.n, c.rung, c.seed, c.model))


def round_rows(cells: list[Cell]) -> list[dict]:
    rows: list[dict] = []
    for cell in cells:
        rows.extend(cell.rounds)
    return rows


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _agreement(values: list) -> float | None:
    values = [str(v) for v in values if v is not None and str(v) not in NON_ACTIONS]
    if len(values) < 2:
        return None
    pairs = list(combinations(values, 2))
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def _kappa(values: list) -> float | None:
    values = [str(v) for v in values if v is not None and str(v) not in NON_ACTIONS]
    if len(values) < 2:
        return None
    observed = _agreement(values)
    if observed is None:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    n = len(values)
    expected = sum((c / n) ** 2 for c in counts.values())
    if expected >= 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def _compliance(bins: dict, verdicts: dict) -> float | None:
    if not verdicts:
        return None
    good = sum(1 for v in verdicts.values() if v in ("ACTION", "WITHHELD"))
    return good / len(verdicts)


def _flag_kinds(row: dict) -> list[str]:
    kinds = row.get("flags") or []
    return [f.get("kind", "") if isinstance(f, dict) else str(f) for f in kinds]


def _q(cell: Cell, row: dict) -> float | None:
    if "q" in row:
        return float(row["q"])
    cap = float(row.get("optimal_profit", 0.0) or 0.0)
    if cap > 0:
        return max(0.0, min(1.0, float(row.get("coalition_profit", 0.0)) / cap))
    return None


# ---------------------------------------------------------------------------
# mutual information with Miller-Madow correction
# ---------------------------------------------------------------------------

def mutual_information(xs: list, ys: list, *, miller_madow: bool = True) -> float:
    """Plug-in MI in bits, optionally Miller-Madow bias corrected."""
    pairs = [(str(x), str(y)) for x, y in zip(xs, ys)
             if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return 0.0
    joint: dict[tuple[str, str], int] = {}
    px: dict[str, int] = {}
    py: dict[str, int] = {}
    for x, y in pairs:
        joint[(x, y)] = joint.get((x, y), 0) + 1
        px[x] = px.get(x, 0) + 1
        py[y] = py.get(y, 0) + 1
    mi = 0.0
    for (x, y), c in joint.items():
        pxy = c / n
        mi += pxy * math.log2(pxy / ((px[x] / n) * (py[y] / n)))
    if miller_madow:
        mi += (len(px) - 1) * (len(py) - 1) / (2.0 * n * math.log(2.0))
    return mi


def pairwise_mi(series: dict[str, list]) -> float | None:
    seats = [s for s, vals in series.items()
             if any(v is not None and str(v) not in NON_ACTIONS for v in vals)]
    if len(seats) < 2:
        return None
    vals = []
    for a, b in combinations(seats, 2):
        vals.append(mutual_information(series[a], series[b]))
    return sum(vals) / len(vals) if vals else None
