"""Read the run tree and write cell-, round-, and detector-level summaries.

    python3 -m analysis.report --runs runs --out analysis_out
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

from . import leg1, leg2, live, meta
from .common import Cell, dedupe_latest, load_cells, round_rows


def _mean(values):
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def _fmt(v, digits=2):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def round_arm_summary(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["scenario"], row["n"], row["rung"], row["model"],
                           row.get("anchor", "")), []).append(row)
    out = []
    for key, items in sorted(groups.items()):
        out.append({
            "scenario": key[0], "n": key[1], "rung": key[2], "model": key[3],
            "anchor": key[4],
            "rounds": len(items),
            "agreement": _mean(r.get("agreement") for r in items),
            "kappa": _mean(r.get("kappa") for r in items),
            "harm_per_round": _mean(r.get("harm") for r in items),
            "q_per_round": _mean(r.get("q") for r in items),
            "messages_per_round": _mean(r.get("messages") for r in items),
            "bytes_per_round": _mean(r.get("bytes") for r in items),
            "compliance": _mean(r.get("compliance") for r in items),
            "uniform_rounds": sum(1 for r in items if r.get("uniform")),
        })
    return out


def _cell_rows(cells: list[Cell]) -> list[dict]:
    rows = []
    for cell in cells:
        rows.append({
            "cell_id": cell.cell_id,
            "attempt": cell.path.name,
            "scenario": cell.scenario,
            "n": cell.n,
            "rung": cell.rung,
            "seed": cell.seed,
            "model": cell.model,
            "anchor": cell.anchor,
            "rounds": len(cell.rounds),
            "harm_total": cell.summary.get("harm_total", 0.0),
            "q_mean": cell.summary.get("q_mean", 0.0),
            "compliance": cell.summary.get("compliance"),
            "messages": cell.summary.get("messages_admitted", 0),
            "rejected": cell.summary.get("messages_rejected", 0),
            "halted": cell.summary.get("halted"),
        })
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def _md_table(rows: list[dict], fields: list[str]) -> str:
    lines = ["| " + " | ".join(fields) + " |",
             "|" + "|".join("---" for _ in fields) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(f)) for f in fields) + " |")
    return "\n".join(lines)


def _print_table(rows: list[dict], fields: list[str]) -> None:
    print(_md_table(rows, fields))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis.report")
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--out", default="analysis_out")
    parser.add_argument("--all-attempts", action="store_true",
                        help="include every attempt instead of the latest per cell")
    parser.add_argument("--include-scripted", action="store_true",
                        help="include scripted/dummy cells")
    parser.add_argument("--permutations", type=int, default=leg1.PERMUTATIONS)
    args = parser.parse_args(argv)

    cells = load_cells(args.runs, include_scripted=True)
    if not args.all_attempts:
        cells = dedupe_latest(cells)
    cells = [c for c in cells if args.include_scripted or not c.scripted]
    if not cells:
        print(f"no cells under {args.runs}")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rounds = round_rows(cells)
    arm_rows = round_arm_summary(rounds)
    cell_rows = _cell_rows(cells)
    leg1_rows = leg1.evaluate(cells, permutations=args.permutations)
    leg2_out = leg2.evaluate(cells)
    live_out = live.evaluate(cells)
    meta_rows = meta.scan_runs(args.runs)

    _write_csv(out_dir / "rounds.csv", rounds)
    _write_csv(out_dir / "round_arms.csv", arm_rows)
    _write_csv(out_dir / "cells.csv", cell_rows)
    _write_csv(out_dir / "leg1.csv", leg1_rows)
    _write_csv(out_dir / "leg2_pairs.csv", leg2_out["pairs"])
    _write_csv(out_dir / "leg2_arms.csv", leg2_out["arms"])
    _write_csv(out_dir / "live.csv", live_out["cells"])
    (out_dir / "leg1.json").write_text(json.dumps(leg1_rows, indent=2),
                                       encoding="utf-8")
    (out_dir / "leg2.json").write_text(json.dumps(leg2_out, indent=2),
                                       encoding="utf-8")
    (out_dir / "live.json").write_text(json.dumps(live_out, indent=2),
                                       encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(meta_rows, indent=2,
                                                  ensure_ascii=False),
                                       encoding="utf-8")

    lines = [
        "# Run report",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')} from `{args.runs}`.",
        f"{len(cells)} cells, {len(rounds)} settled rounds.",
        "",
        "## Cells",
        "",
        _md_table(cell_rows, ["cell_id", "scenario", "n", "rung", "seed",
                              "model", "anchor", "rounds", "harm_total", "q_mean",
                              "compliance", "messages"]),
        "",
        "## Round-wise summaries",
        "",
        "One row per arm (scenario x N x rung x model), averaged over rounds.",
        "",
        _md_table(arm_rows, ["scenario", "n", "rung", "model", "anchor", "rounds",
                             "agreement", "kappa", "harm_per_round",
                             "q_per_round", "messages_per_round",
                             "bytes_per_round", "compliance",
                             "uniform_rounds"]),
        "",
        "### Per-cell rounds",
        "",
    ]
    for cell in cells:
        lines.append(f"**{cell.cell_id}** `{cell.path.name}` · "
                     f"{cell.model}{('/' + cell.anchor) if cell.anchor else ''} · "
                     f"N={cell.n} · rung={cell.rung} · seed={cell.seed}")
        lines.append("")
        lines.append(_md_table(cell.rounds, ["round", "harm", "q", "agreement",
                                            "kappa", "messages", "bytes",
                                            "compliance"]))
        lines.append("")

    lines += ["## Leg 1 — excess action agreement", ""]
    if leg1_rows:
        lines.append(_md_table(leg1_rows, [
            "cell_id", "model", "anchor", "n", "rung", "seed", "agreement",
            "agreement_baseline", "excess", "permutation_p",
            "permutation_p_paired", "permutation_p_within", "kappa",
            "mi_bits", "corroborators", "harm", "claim"]))
    else:
        lines.append("No treatment cells with a matched 0* baseline.")

    lines += ["", "## Leg 2 — harm against 0*", ""]
    if leg2_out["pairs"]:
        lines.append(_md_table(leg2_out["pairs"], [
            "cell_id", "n", "rung", "seed", "harm", "harm_baseline",
            "harm_diff", "q", "q_baseline"]))
        lines += ["", "### By arm", "",
                  _md_table(leg2_out["arms"], [
                      "scenario", "n", "rung", "model", "seeds", "harm_mean",
                      "baseline_mean", "diff_mean", "positive_seeds",
                      "sign_test_p"])]
    else:
        lines.append("No matched treatment/baseline pairs.")

    lines += ["", "## Live health", ""]
    if live_out["cells"]:
        lines.append(_md_table(live_out["cells"], [
            "cell_id", "scenario", "n", "rung", "seed", "rounds", "compliance",
            "harm_total", "q_mean", "messages", "zero_message_rounds", "halted"]))
    else:
        lines.append("No model-backed cells.")

    flagged = [row for row in meta_rows if row["scan_hits"] or row["engine_meta_hits"]]
    lines += ["", "## Meta scan", "",
              f"{len(meta_rows)} transcripts; {len(flagged)} flagged."]
    for row in flagged[:40]:
        lines.append(f"- `{row['cell_id']}`: {len(row['scan_hits'])} scan hits, "
                     f"{row['engine_meta_hits']} engine hits")
        for hit in row["scan_hits"][:3]:
            lines.append(f"  - {hit['label']} (line {hit['line']}): {hit['excerpt']}")

    report = "\n".join(lines) + "\n"
    (out_dir / "report.md").write_text(report, encoding="utf-8")

    print(f"wrote {out_dir}/report.md")
    print()
    print("Round-wise summary by arm:")
    _print_table(arm_rows, ["scenario", "n", "rung", "model", "anchor", "rounds",
                            "agreement", "kappa", "harm_per_round",
                            "messages_per_round", "compliance"])
    if leg1_rows:
        print()
        print("Leg 1:")
        _print_table(leg1_rows, ["cell_id", "model", "anchor", "n", "rung",
                                 "seed", "agreement", "agreement_baseline",
                                 "excess", "permutation_p", "corroborators",
                                 "harm", "claim"])
    if flagged:
        print()
        print(f"{len(flagged)} transcript(s) flagged; see {out_dir}/meta.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
