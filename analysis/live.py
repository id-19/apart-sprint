"""Live-cell health: compliance, verdicts, messages, and flags by round."""

from __future__ import annotations

import statistics

from .common import Cell


def evaluate(cells: list[Cell]) -> dict:
    rows = []
    for cell in cells:
        if cell.scripted:
            continue
        rounds = cell.rounds
        flag_counts: dict[str, int] = {}
        for row in rounds:
            for kind in row.get("flags") or []:
                flag_counts[kind] = flag_counts.get(kind, 0) + 1
        rows.append({
            "cell_id": cell.cell_id,
            "attempt": cell.path.name,
            "scenario": cell.scenario,
            "n": cell.n,
            "rung": cell.rung,
            "seed": cell.seed,
            "model": cell.model,
            "rounds": len(rounds),
            "compliance": cell.summary.get("compliance"),
            "action_rate": cell.summary.get("action_rate"),
            "noncompliance": cell.summary.get("noncompliance"),
            "verdicts": cell.summary.get("verdict_counts", {}),
            "harm_total": cell.summary.get("harm_total", 0.0),
            "q_mean": cell.summary.get("q_mean", 0.0),
            "messages": cell.summary.get("messages_admitted", 0),
            "rejected": cell.summary.get("messages_rejected", 0),
            "zero_message_rounds": flag_counts.get("ZERO_MESSAGES", 0),
            "flags": flag_counts,
            "halted": cell.summary.get("halted"),
        })
    rows.sort(key=lambda r: (r["scenario"], r["n"], r["rung"], r["seed"], r["cell_id"]))
    return {"cells": rows}


def by_arm(cells: list[Cell]) -> list[dict]:
    groups: dict[tuple, list[Cell]] = {}
    for cell in cells:
        if cell.scripted:
            continue
        groups.setdefault((cell.scenario, cell.n, cell.rung), []).append(cell)
    out = []
    for key, items in sorted(groups.items()):
        out.append({
            "scenario": key[0], "n": key[1], "rung": key[2],
            "attempts": len(items),
            "compliance": statistics.fmean(
                float(c.summary.get("compliance", 0.0) or 0.0) for c in items),
            "harm": statistics.fmean(
                float(c.summary.get("harm_total", 0.0) or 0.0) for c in items),
            "q": statistics.fmean(
                float(c.summary.get("q_mean", 0.0) or 0.0) for c in items),
            "messages": statistics.fmean(
                float(c.summary.get("messages_admitted", 0) or 0.0) for c in items),
        })
    return out
