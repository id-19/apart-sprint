"""Print one cell's agent trajectories, grouped by cycle, exchange, and seat.

    python3 -m analysis.trajectory --run runs/s4_n3_b2048_s0_a4
    python3 -m analysis.trajectory --run runs/... --seat A --full
    python3 -m analysis.trajectory --run runs/... --summary
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return rows


def _clip(text: str, limit: int, full: bool) -> str:
    text = (text or "").strip()
    if full or len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …"


def _grouped(rows: list[dict]) -> dict[tuple[int, int, str], dict]:
    groups: dict[tuple[int, int, str], dict] = {}
    for row in rows:
        key = (int(row.get("cycle", 0)), int(row.get("exchange", 0)),
               row.get("seat", ""))
        group = groups.setdefault(key, {"model": None, "calls": []})
        if "tool_call" in row:
            group["calls"].append(row)
        else:
            group["model"] = row
    return groups


def render(run_dir: Path, *, seat: str | None = None, cycle: int | None = None,
           full: bool = False, limit: int = 400) -> str:
    rows = _load(run_dir / "trajectory.jsonl")
    if not rows:
        return f"no trajectory.jsonl under {run_dir}"
    groups = _grouped(rows)
    lines = [f"# {run_dir.name}"]
    cell = _load_json(run_dir / "cell.json")
    summary = _load_json(run_dir / "summary.json")
    if cell:
        lines.append(f"{cell.get('scenario')} · N={cell.get('n')} · "
                     f"rung={cell.get('rung')} · seed={cell.get('seed')}")
    if summary:
        lines.append(f"model={summary.get('model')} harm={summary.get('harm_total')} "
                     f"q={summary.get('q_mean')} compliance={summary.get('compliance')}")
    lines.append("")
    for (c, e, s), group in sorted(groups.items()):
        if seat and s != seat:
            continue
        if cycle is not None and c != cycle:
            continue
        model = group["model"] or {}
        calls = group["calls"]
        lines.append(f"## cycle {c} · exchange {e} · seat {s}")
        thinking = _clip(model.get("thinking", ""), limit, full)
        content = _clip(model.get("content", ""), limit, full)
        if thinking:
            lines.append(f"thinking: {thinking}")
        if content:
            lines.append(f"content: {content}")
        if model.get("usage"):
            usage = model["usage"]
            lines.append(f"usage: in={usage.get('prompt_eval_count')} "
                         f"out={usage.get('eval_count')} "
                         f"latency={model.get('latency_s', 0):.1f}s")
        for call in calls:
            fn = call.get("tool_call") or {}
            name = fn.get("name", "?")
            args = json.dumps(fn.get("arguments", {}), ensure_ascii=False)
            result = _clip(call.get("tool_result", ""), limit, full)
            flag = "" if call.get("ok", True) else " [rejected]"
            lines.append(f"call {name}{flag} {args}")
            if result:
                lines.append(f"  -> {result}")
        if not model and not calls:
            lines.append("(no record)")
        lines.append("")
    return "\n".join(lines)


def summary(run_dir: Path) -> str:
    rows = _load(run_dir / "trajectory.jsonl")
    groups = _grouped(rows)
    lines = [f"# {run_dir.name} — exchange summary", ""]
    for (c, e, s), group in sorted(groups.items()):
        model = group["model"] or {}
        names = [((call.get("tool_call") or {}).get("name", "?"))
                 for call in group["calls"]]
        think = len(model.get("thinking", "") or "")
        text = len(model.get("content", "") or "")
        lines.append(f"c{c:02d} e{e} {s}: calls={','.join(names) or '-'} "
                     f"think={think}c text={text}c")
    return "\n".join(lines)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis.trajectory")
    parser.add_argument("--run", required=True)
    parser.add_argument("--seat", default=None)
    parser.add_argument("--cycle", type=int, default=None)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--limit", type=int, default=400)
    args = parser.parse_args(argv)
    run_dir = Path(args.run)
    if args.summary:
        print(summary(run_dir))
    else:
        print(render(run_dir, seat=args.seat, cycle=args.cycle,
                     full=args.full, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
