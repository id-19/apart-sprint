"""Live terminal watch of a running matrix scenario.

Follows run dirs under runs/<scenario>_* and prints one line per completed
cycle (harm, admitted messages, per-seat bins) plus cell start, cell finish,
and any realism halt.  Existing state is not replayed; only new events print.

    python3 -m analysis.watch s1
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

POLL = 5.0
CYCLES = {"s1": 8, "s2": 10, "s3": 8, "s4": 8}


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def _say(text: str) -> None:
    print(f"{_ts()}  {text}")
    sys.stdout.flush()


def _num(x) -> str:
    try:
        return f"{float(x):,.0f}"
    except (TypeError, ValueError):
        return str(x)


def main(argv: list[str]) -> int:
    scenario = argv[0] if argv else "s1"
    total = CYCLES.get(scenario, 8)
    settlements_seen: dict[Path, int] = {}
    flags_seen: dict[Path, int] = {}
    done: set[Path] = set(p.parent for p in
                          Path("runs").glob(f"{scenario}_*/summary.json")
                          if time.time() - p.stat().st_mtime > 120)
    _say(f"watching runs/{scenario}_* — new rounds print here (Ctrl-C to stop)")
    while True:
        cells = [p for p in Path("runs").glob(f"{scenario}_*_a*")
                 if p.is_dir() and "_a" in p.name]
        cells.sort(key=lambda p: p.stat().st_mtime)
        for cell_dir in cells:
            settle = cell_dir / "settlement.jsonl"
            if settle.exists():
                lines = settle.read_text().splitlines()
                if cell_dir not in settlements_seen:
                    if cell_dir not in done and \
                            time.time() - settle.stat().st_mtime < 300:
                        settlements_seen[cell_dir] = 0
                        _say(f"▶ {cell_dir.name} — in flight")
                    else:
                        settlements_seen[cell_dir] = len(lines)
                        continue
                for line in lines[settlements_seen[cell_dir]:]:
                    r = json.loads(line)
                    bins = r.get("bins") or {}
                    seats = " ".join(f"{k}={v}" for k, v in bins.items())
                    verdicts = list((r.get("verdicts") or {}).values())
                    bad = sum(1 for v in verdicts
                              if v not in ("ACTION", "WITHHELD"))
                    _say(f"{r['cell_id']}  c{r['cycle'] + 1}/{total}  "
                         f"harm {_num(r.get('harm'))} · "
                         f"msgs {r.get('messages_admitted', 0)} "
                         f"({r.get('admitted_bytes', 0)} chars)"
                         + (f" · ⚠ {bad} noncompliant" if bad else "")
                         + (f" · {seats}" if seats else ""))
                settlements_seen[cell_dir] = len(lines)
            flags = cell_dir / "live_flags.jsonl"
            if flags.exists():
                lines = flags.read_text().splitlines()
                if cell_dir not in flags_seen:
                    flags_seen[cell_dir] = len(lines)
                else:
                    for line in lines[flags_seen[cell_dir]:]:
                        r = json.loads(line)
                        kind = r.get("label") or r.get("type") or "flag"
                        what = str(r.get("excerpt") or r.get("detail") or "")[:100]
                        marker = "⛔" if r.get("label") else "⚡"
                        _say(f"{marker} {cell_dir.name} {kind}"
                             + (f" — {what}" if what else ""))
                    flags_seen[cell_dir] = len(lines)
            summary = cell_dir / "summary.json"
            if summary.exists() and cell_dir not in done:
                done.add(cell_dir)
                s = json.loads(summary.read_text())
                if s.get("halted"):
                    first = (s.get("flags") or [{}])[0]
                    _say(f"■ {cell_dir.name} HALTED: {s.get('halt_reason') or first.get('label', '?')}")
                else:
                    _say(f"✓ {cell_dir.name} — harm {_num(s['harm_total'])}, "
                         f"msgs {s['messages_admitted']}, "
                         f"compliance {s['compliance']:.2f}")
        time.sleep(POLL)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
