"""Per-agent, per-turn, per-round view of one cell.

    python3 -m analysis.trace runs/s1_n4_b128_s2
    python3 -m analysis.trace --cell s1_n4_b128_s2 --runs runs
    python3 -m analysis.trace runs/s1_n4_b128_s2 --prompts --seat B --cycle 2

Reads the records the engine writes and prints them in world order:

    cycle N
      exchange k
        seat A: tool calls (a filing, a posted note, a read)
      settlement
        A filed 1,150 | B filed 1,200 | ...   harm 2,130   verdicts

With ``--prompts`` it prints the exact request sent to the model (the full
system and user messages) for a seat, cycle and optionally exchange.  Those
requests are stored verbatim in ``raw_calls.jsonl``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _call_text(call: dict) -> str:
    fn = call.get("function") or {}
    name = fn.get("name", "?")
    raw = fn.get("arguments")
    if isinstance(raw, str):
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {"raw": raw}
    else:
        args = raw or {}
    interesting = ["text", "message", "price", "note", "decision", "status",
                   "orders", "rating", "to", "recipient", "recipients"]
    body = {k: v for k, v in args.items() if k in interesting}
    if not body:
        body = args
    return f"{name} {json.dumps(body, ensure_ascii=False)[:400]}"


def find_cell(target: str, runs: Path) -> Path:
    path = Path(target)
    if path.is_dir():
        return path
    for cell_json in runs.rglob("cell.json"):
        try:
            meta = json.loads(cell_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("cell_id") == target:
            return cell_json.parent
    raise SystemExit(f"no cell {target!r} under {runs}")


def show_turns(cell: Path) -> None:
    calls = _rows(cell / "raw_calls.jsonl")
    settles = {row.get("cycle"): row for row in _rows(cell / "settlement.jsonl")}
    by_cycle: dict[int, list[dict]] = {}
    for call in calls:
        by_cycle.setdefault(int(call.get("cycle") or 0), []).append(call)

    for cycle in sorted(by_cycle):
        print(f"\n## Cycle {cycle + 1}")
        exchanges: dict[int, list[dict]] = {}
        for call in by_cycle[cycle]:
            exchanges.setdefault(int(call.get("exchange") or 0), []).append(call)
        for exchange in sorted(exchanges):
            print(f"\n  exchange {exchange}")
            for call in exchanges[exchange]:
                seat = call.get("seat", "?")
                resp = call.get("response") or {}
                msg = resp.get("message") or {}
                for fn in msg.get("tool_calls") or []:
                    print(f"    {seat}: {_call_text(fn)}")
                content = (msg.get("content") or "").strip()
                if content:
                    print(f"    {seat} (said): {content[:300]}")
                if call.get("status") not in (None, "ok"):
                    print(f"    {seat}: status {call.get('status')}")
        row = settles.get(cycle)
        if row:
            bins = row.get("bins") or {}
            verdicts = row.get("verdicts") or {}
            filed = " | ".join(f"{s} -> {bins.get(s, '-')} ({verdicts.get(s, '-')})"
                               for s in sorted(bins))
            print(f"\n  settled: {filed}")
            print(f"  harm {row.get('harm')}  messages "
                  f"{row.get('messages_admitted')} admitted / "
                  f"{row.get('messages_rejected')} rejected  "
                  f"bytes {row.get('admitted_bytes')}")


def show_prompts(cell: Path, seat: str, cycle: int | None,
                 exchange: int | None) -> None:
    for call in _rows(cell / "raw_calls.jsonl"):
        if seat and call.get("seat") != seat:
            continue
        if cycle is not None and int(call.get("cycle") or 0) != cycle:
            continue
        if exchange is not None and int(call.get("exchange") or 0) != exchange:
            continue
        req = call.get("request") or {}
        print(f"\n### seat {call.get('seat')} cycle {call.get('cycle')} "
              f"exchange {call.get('exchange')} model {call.get('model')}")
        for message in req.get("messages") or []:
            print(f"\n[{message.get('role')}]\n{message.get('content')}")
        return
    print("no matching request recorded")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis.trace")
    parser.add_argument("target", nargs="?", default=None,
                        help="cell directory or id")
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--cell", default=None)
    parser.add_argument("--prompts", action="store_true")
    parser.add_argument("--seat", default=None)
    parser.add_argument("--cycle", type=int, default=None,
                        help="1-based cycle number")
    parser.add_argument("--exchange", type=int, default=None)
    args = parser.parse_args(argv)

    target = args.target or args.cell
    if not target:
        raise SystemExit("give a cell directory or --cell id")
    cell = find_cell(target, Path(args.runs))
    print(f"# {cell.name}")
    summary = cell / "summary.json"
    if summary.exists():
        data = json.loads(summary.read_text(encoding="utf-8"))
        print(f"harm {data.get('harm_total')}  q {data.get('q_mean')}  "
              f"compliance {data.get('compliance')}  "
              f"messages {data.get('messages_admitted')}  "
              f"engine {data.get('engine_version')} "
              f"scenario {data.get('scenario_version')}")
    if args.prompts:
        cycle = None if args.cycle is None else args.cycle - 1
        show_prompts(cell, args.seat or "", cycle, args.exchange)
    else:
        show_turns(cell)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
