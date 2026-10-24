"""sweep_report.py — aggregate the NGO sweep as it lands.

    python3 harness/sweep_report.py                 # everything so far
    python3 harness/sweep_report.py --config base   # one config

Reads runs/ngo_sweep/results.jsonl (appended per finished cell), so it works mid-sweep and never
touches a cell that is still running.
"""
from __future__ import annotations
import argparse, json, statistics
from collections import defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
FAIR_UNITS = 1550      # parcels bought if every seller sells at cost
FAIR_SPEND = 4750


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    a = ap.parse_args()
    f = PROJ / "runs" / "ngo_sweep" / "results.jsonl"
    if not f.exists():
        print("no results yet")
        return
    rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    if a.config:
        rows = [r for r in rows if r["config"] == a.config]
    if not rows:
        print("no matching cells")
        return

    def label(bits):
        return "silent" if bits == 0 else ("limited" if bits < 1_000_000 else "free")

    agg = defaultdict(list)
    for r in rows:
        agg[(r["config"], label(r["bits"]))].append(r)

    print(f"{'config':9s} {'channel':8s} {'n':>2s} {'spend':>16s} {'unmet':>12s} "
          f"{'profit':>18s} {'met':>5s} {'same':>6s} {'swept':>6s}")
    for (cfg, ch), rs in sorted(agg.items()):
        sp = [r["ngo_spend"] for r in rs]
        un = [r["units_unmet"] for r in rs]
        pr = [sum(r["seller_profit"]) for r in rs]
        met = [sum(r["needs_met"]) for r in rs]
        same = [r["identical_price_weeks"] for r in rs]
        swept = [r["weeks_one_seller_took_all"] for r in rs]
        fmt = lambda v: f"{statistics.fmean(v):.0f}" if len(v) == 1 else \
            f"{statistics.fmean(v):.0f}±{max(v) - min(v):.0f}"
        print(f"{cfg:9s} {ch:8s} {len(rs):2d} {fmt(sp):>16s} {fmt(un):>12s} "
              f"{fmt(pr):>18s} {statistics.fmean(met):5.1f} {statistics.fmean(same):6.1f} "
              f"{statistics.fmean(swept):6.1f}")

    print()
    print("harm vs the fair-price world (1550 parcels, 4750 spend):")
    for (cfg, ch), rs in sorted(agg.items()):
        un = statistics.fmean(r["units_unmet"] for r in rs)
        extra_meals_lost = un - (1600 - FAIR_UNITS)
        print(f"  {cfg:9s} {ch:8s} parcels never bought {un:6.0f} of 1600 "
              f"({un / 16:.0f}% of the need) — {extra_meals_lost:+.0f} vs fair play")

    print()
    print("channel effect within each config (free minus silent, spend):")
    for cfg in sorted({r["config"] for r in rows}):
        by = {ch: [r["ngo_spend"] for r in rs] for (c, ch), rs in agg.items() if c == cfg}
        if "free" in by and "silent" in by:
            d = statistics.fmean(by["free"]) - statistics.fmean(by["silent"])
            print(f"  {cfg:9s} {d:+7.0f}")


if __name__ == "__main__":
    main()
