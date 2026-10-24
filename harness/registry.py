"""registry.py — one durable index over every cell ever run, so data can be cleaned and reused later.

Nothing here changes a run. It reads `runs/`, labels each cell (task, arm, model, seed, validity),
records how to re-read its files, and writes:

    runs/REGISTRY.json   machine-readable index, one entry per cell
    runs/REGISTRY.md     human table

A cell is marked INVALID if its task directory carries an INVALID.md (the seed_v0 clobbering case).
Invalid cells stay indexed — deleting them would erase the record of what went wrong.

Reuse:
    from registry import load_cells
    cells = load_cells(task="seed_v0b")            # every valid cell of one task
    cells = load_cells(arm="free", valid_only=True)
    for c in cells: c["transcript"], c["trajectory"], c["summary"]   # absolute paths
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RUNS = PROJ / "runs"
OUT_JSON = RUNS / "REGISTRY.json"
OUT_MD = RUNS / "REGISTRY.md"

# task directory -> what the task actually is. Extend as new tasks are added.
TASK_LABELS = {
    "seed_v0": "T0 common release, equal deadlines, one order/seat, no firing (CLOBBERED — invalid)",
    "seed_v0b": "T0 common release, equal deadlines, one order/seat, no firing",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else ""


def scan():
    cells = []
    for summ in sorted(RUNS.rglob("summary.json")):
        d = summ.parent
        s = json.loads(summ.read_text())
        task_dir = d.parent if d.parent != RUNS else d
        # a cell dir is either runs/<task>/<cell>/ or runs/<task>/<arm>/<cell>/
        rel = d.relative_to(RUNS)
        task = rel.parts[0]
        invalid = (RUNS / task / "INVALID.md").exists()
        cells.append({
            "cell_id": f"{task}__{'free' if s['bits'] > 0 else 'silent'}__"
                       f"{s['model'].replace(':', '-')}__s{s['seed']}__{d.name}",
            "task": task,
            "task_label": TASK_LABELS.get(task, task),
            "valid": not invalid,
            "invalid_reason": ("task directory carries INVALID.md — see runs/%s/INVALID.md" % task)
                              if invalid else "",
            "arm": "free" if s["bits"] > 0 else "silent",
            "model": s["model"],
            "seed": s["seed"],
            "bits_per_day": s.get("bits", 0),
            "seats": s.get("seats"), "days": s.get("days"), "lots": s.get("lots"),
            "impact_lots": s.get("impact_lots"), "sigma": s.get("sigma"),
            "calls": s.get("calls"), "mean_latency_s": s.get("latency_mean"),
            "total_cost": s.get("total_cost"), "per_seat_cost": s.get("per_seat_cost"),
            "days_used": s.get("days_used"), "n_distinct_days": s.get("n_distinct_days"),
            "channel_bits": s.get("admitted_bits", 0), "empty_messages": s.get("empty_messages"),
            "malformed": s.get("malformed"), "forced_fills": s.get("forced_fills", 0),
            "written": datetime.fromtimestamp(summ.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "dir": str(d.relative_to(PROJ)),
            "summary": str(summ.relative_to(PROJ)),
            "transcript": str((d / "transcript.md").relative_to(PROJ)),
            "trajectory": str((d / "trajectory.jsonl").relative_to(PROJ)),
            "hash_summary": sha(summ),
            "hash_transcript": sha(d / "transcript.md"),
        })
    return cells


def load_cells(task=None, arm=None, valid_only=True):
    """Reuse entry point. Returns cells with absolute file paths attached."""
    cells = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else scan()
    out = []
    for c in cells:
        if valid_only and not c["valid"]:
            continue
        if task and c["task"] != task:
            continue
        if arm and c["arm"] != arm:
            continue
        c = dict(c)
        for k in ("dir", "summary", "transcript", "trajectory"):
            c[k] = str(PROJ / c[k]) if not Path(c[k]).is_absolute() else c[k]
        out.append(c)
    return out


def main():
    cells = scan()
    RUNS.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(cells, indent=2))
    valid = [c for c in cells if c["valid"]]
    lines = ["# Cell registry", "",
             f"Built {datetime.now():%Y-%m-%d %H:%M}. {len(cells)} cells, {len(valid)} valid, "
             f"{len(cells) - len(valid)} quarantined.", "",
             "Reuse with `from registry import load_cells`. Invalid cells stay listed on purpose — "
             "they are the record of what went wrong.", "",
             "| cell | task | arm | model | total cost | days used | bits | valid |",
             "|---|---|---|---|---|---|---|---|"]
    for c in cells:
        lines.append(f"| `{c['cell_id']}` | {c['task']} | {c['arm']} | {c['model']} | "
                     f"{c['total_cost']} | {c['days_used']} | {c['channel_bits']} | "
                     f"{'yes' if c['valid'] else 'NO'} |")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"registry: {len(cells)} cells ({len(valid)} valid) -> {OUT_JSON.relative_to(PROJ)}")
    for c in cells:
        flag = "" if c["valid"] else "  [INVALID]"
        tc = f"{c['total_cost']:>7}" if isinstance(c["total_cost"], (int, float)) else "    n/a"
        print(f"  {c['cell_id']:60s} total {tc}  {flag}")


if __name__ == "__main__":
    main()
