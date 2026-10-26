"""Render the three report figures from the run tree.

Only finished cells with a summary are read.  v15 cells predate the stored
benchmark, so the benchmark is rebuilt from the scenario (it depends on the
seed alone) and the percentage is recomputed for them.
"""

import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from harness2.scenarios.s1 import S1  # noqa: E402

RUNS = os.path.join(ROOT, "actual experiment", "runs")
OUT = os.path.dirname(os.path.abspath(__file__))

# Reference palette, categorical slots 1-3 (validated all-pairs, light mode).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e0"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2,
    "text.color": INK,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "semibold",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def benchmarks(seats=("A", "B", "C", "D"), seeds=range(6)):
    sc = S1()
    out = {}
    for seed in seeds:
        world = sc.make_world(list(seats), seed)
        sc.warmup(world, list(seats))
        total = 0.0
        for cycle in range(sc.cycles):
            sc.new_round(world, cycle)
            world["actions"] = {s: {"price": world["sellers"][s]["cost"]}
                                for s in seats}
            rec = sc.settle(world)
            total += sum(rec["counterfactual_benchmark"][b["id"]] * b["need"]
                         for b in world["buyers"])
        out[seed] = total
    return out


def cells():
    bench = benchmarks()
    rows = []
    for path in glob.glob(os.path.join(RUNS, "*", "summary.json")):
        s = json.load(open(path))
        if s.get("halted") or not s.get("harm_total"):
            continue
        cid = s["cell_id"]
        parts = cid.split("_")
        if parts[0] != "s1" or parts[1] != "n4":
            continue
        seed = int(parts[3][1:])
        pct = s.get("harm_over_cost_pct")
        if pct is None:
            pct = 100.0 * s["harm_total"] / bench[seed]
        coll = (s.get("measure") or {}).get("collusion") or {}
        rows.append({
            "model": s["model"].split(":")[0],
            "version": s.get("scenario_version"),
            "rung": int(parts[2][1:]),
            "seed": seed,
            "pct": pct,
            "agree": coll.get("mean_agreement"),
            "compliance": s.get("compliance"),
        })
    return rows


def mean_by(rows, key, field):
    """Mean of ``field`` per rung, with the rung converted to its realised
    per-seat allowance at N=4 (4 x rung characters per seat per cycle)."""
    buckets = {}
    for r in rows:
        if r[field] is None:
            continue
        buckets.setdefault(4 * r[key], []).append(r[field])
    return {k: (sum(v) / len(v), len(v)) for k, v in buckets.items()}


def draw(ax, series, label_fmt="{:.0f}%", ylim=None, ylabel="", y_offsets=None):
    y_offsets = y_offsets or {}
    for name, (data, color) in series.items():
        xs = sorted(data)
        ys = [data[x][0] for x in xs]
        ns = [data[x][1] for x in xs]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2,
                solid_capstyle="round", zorder=3, label=name)
        for x, y, n in zip(xs, ys, ns):
            dx, dy = y_offsets.get(name, (0, 11))
            ax.annotate(label_fmt.format(y), (x, y), textcoords="offset points",
                        xytext=(dx, dy), ha="center", fontsize=9, color=INK_2)
    ax.set_xlabel("characters per seat per cycle")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.set_xticks([0, 128, 256, 512, 1024, 2048])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.set_xlim(-90, 2250)
    if ylim:
        ax.set_ylim(*ylim)
    ax.legend(frameon=False, loc="center right", labelcolor=INK_2, fontsize=9)


def message_counts():
    """Attempts, admissions and refusals per realised allowance, pooled over
    every finished S1 cell that has a message log."""
    tally = {}
    for path in glob.glob(os.path.join(RUNS, "*", "messages.jsonl")):
        cell_dir = os.path.dirname(path)
        cid = os.path.basename(cell_dir)
        summary = os.path.join(cell_dir, "summary.json")
        if not cid.startswith("s1_n4") or not os.path.exists(summary):
            continue
        if json.load(open(summary)).get("halted"):
            continue
        chars = 4 * int(cid.split("_")[2][1:])
        bucket = tally.setdefault(chars, {"admitted": 0, "rejected": 0, "cells": set()})
        bucket["cells"].add(cid)
        for line in open(path):
            disp = json.loads(line).get("disposition")
            if disp in ("admitted", "rejected"):
                bucket[disp] += 1
    return tally


def draw_messages(ax, tally):
    xs = sorted(k for k in tally if k > 0)
    admitted = [tally[x]["admitted"] for x in xs]
    rejected = [tally[x]["rejected"] for x in xs]
    ax.bar(xs, admitted, width=110, color=BLUE, label="delivered",
           edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.bar(xs, rejected, bottom=admitted, width=110, color=ORANGE,
           label="refused: longer than the allowance left",
           edgecolor=SURFACE, linewidth=2, zorder=3)
    for x, a, r in zip(xs, admitted, rejected):
        share = 100 * r / max(1, a + r)
        ax.annotate(f"{share:.0f}% refused", (x, a + r), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=9, color=INK_2)
    ax.set_xlabel("characters per seat per cycle")
    ax.set_ylabel("message attempts, all finished S1 cells")
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.set_xticks([128, 256, 512, 2048])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.set_xlim(0, 2200)
    ax.set_ylim(0, 135)
    ax.legend(frameon=False, loc="upper right", labelcolor=INK_2, fontsize=9)


def main():
    rows = cells()
    dose = [r for r in rows if r["version"] == "15"]
    sal = [r for r in rows if r["version"] == "17"]

    # Figure 1 and 2: the dose arm.
    colors = {"gemma4": BLUE, "gpt-oss": ORANGE, "deepseek-v4.1-flash": AQUA}
    names = {"gemma4": "gemma4 (2–3 seeds)", "gpt-oss": "gpt-oss:120b (1 seed)",
             "deepseek-v4.1-flash": "deepseek-v4.1-flash (1 seed)"}
    fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=200)
    series = {}
    for m, c in colors.items():
        pts = mean_by([r for r in dose if r["model"] == m], "rung", "pct")
        if pts:
            series[names[m]] = (pts, c)
    draw(ax, series, ylabel="overcharge, % over cost benchmark",
          ylim=(-1.5, 52),
          y_offsets={names["gpt-oss"]: (0, -14), names["deepseek-v4.1-flash"]: (0, 13)})
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1_harm_by_rung.png"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=200)
    series = {}
    for m, c in colors.items():
        pts = mean_by([r for r in dose if r["model"] == m], "rung", "agree")
        if pts:
            series[names[m]] = (pts, c)
    draw(ax, series, label_fmt="{:.2f}", ylim=(0, 1.12),
         ylabel="mean pairwise price agreement",
         y_offsets={names["gemma4"]: (-16, 8), names["gpt-oss"]: (18, 6),
                    names["deepseek-v4.1-flash"]: (0, -17)})
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig2_agreement_by_rung.png"))
    plt.close(fig)

    # Figure 3: the salience arm.
    fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=200)
    series = {}
    sal_names = {"gemma4": "gemma4 (1–2 seeds)", "gpt-oss": "gpt-oss:120b (2 seeds)"}
    for m, c in (("gemma4", BLUE), ("gpt-oss", ORANGE)):
        pts = mean_by([r for r in sal if r["model"] == m], "rung", "pct")
        if pts:
            series[sal_names[m]] = (pts, c)
    draw(ax, series, ylabel="overcharge, % over cost benchmark")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_salience_by_rung.png"))
    plt.close(fig)

    # Figure 4: what the ledger does to the smallest channels.
    tally = message_counts()
    fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=200)
    draw_messages(ax, tally)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4_refused_messages.png"))
    plt.close(fig)

    print("wrote", ", ".join(sorted(os.path.basename(p) for p in glob.glob(OUT + "/*.png"))))


if __name__ == "__main__":
    main()
