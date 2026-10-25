"""Per-model comparison over the S1 sweep cells.

    python3 -m analysis.model_compare

Reads every summary.json under runs/, keeps complete unhalted S1 cells, and
prints one block per model: cells, harm by rung, messages, compliance.  Only
the highest-attempt summary per (model, cell_id) counts, so resumed cells are
not double-counted.  Costs no model calls.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def _latest_per_cell() -> dict[tuple[str, str], dict]:
    from harness2.engine import ENGINE_VERSION
    from harness2.scenario import load_scenario
    prompt_version = load_scenario("s1").version
    best: dict[tuple[str, str], dict] = {}
    paths = sorted(Path("runs").glob("s1_*/summary.json"),
                   key=lambda p: p.stat().st_mtime)
    for p in paths:
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if s.get("halted"):
            continue
        if s.get("cycles_run", 0) < 8:
            continue
        # Only cells on the current prompt and engine versions are comparable;
        # anything older is excluded by the same gates the resume rule uses.
        if s.get("scenario_version") != prompt_version:
            continue
        if s.get("engine_version") != ENGINE_VERSION:
            continue
        key = (s.get("model", "?"), s.get("cell_id", "?"))
        best[key] = s          # later mtime wins
    return best


def main() -> int:
    best = _latest_per_cell()
    models: dict[str, list[dict]] = defaultdict(list)
    for (model, _), s in best.items():
        models[model].append(s)
    if not models:
        print("no complete cells yet")
        return 1
    for model in sorted(models):
        rows = sorted(models[model], key=lambda s: (s["rung"], s["seed"]))
        print(f"\n{model}  ({len(rows)} complete cells)")
        print(f"  {'cell':<20} {'rung':>5} {'seed':>4} {'harm':>9} {'msgs':>5} "
              f"{'chars':>7} {'comp':>5}")
        for s in rows:
            chars = sum(c.get("admitted_bytes", 0)
                        for c in s.get("per_cycle", []))
            print(f"  {s['cell_id']:<20} {s['rung']:>5} {s['seed']:>4} "
                  f"{s.get('harm_total', 0):>9,.0f} {s.get('messages_admitted', 0):>5} "
                  f"{chars:>7} {s.get('compliance', 0):>5.2f}")
        by_rung: dict[int, list[float]] = defaultdict(list)
        msg_rung: dict[int, list[int]] = defaultdict(list)
        for s in rows:
            by_rung[s["rung"]].append(s.get("harm_total", 0.0))
            msg_rung[s["rung"]].append(s.get("messages_admitted", 0))
        for rung in sorted(by_rung):
            harms = by_rung[rung]
            msgs = msg_rung[rung]
            print(f"  rung {rung:>5}: mean harm {sum(harms)/len(harms):>9,.0f} "
                  f"(n={len(harms)}) · mean msgs {sum(msgs)/max(1, len(msgs)):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
