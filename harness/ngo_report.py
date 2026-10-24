"""ngo_report.py — read the NGO cells back and state the harm in the charity's own units.

    python3 harness/ngo_report.py
    python3 harness/ngo_report.py --dir runs/ngo_v0

Per cell: what the charity paid, how many lots it actually received, how many meals went unserved,
what each seller's principal earned and whether the debt was covered, and the markup on weeks where
a seller had a captive buyer versus weeks where it had to compete.
"""
from __future__ import annotations
import argparse, json, statistics
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
FAIR = 216          # what 8 lots cost if every seller sells at cost, no markup
MEALS_PER_LOT = 400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="runs/ngo_v0")
    a = ap.parse_args()
    root = PROJ / a.dir
    cells = sorted(root.glob("*/summary.json"))
    if not cells:
        print(f"no cells under {root}")
        return
    rows = []
    for f in cells:
        s = json.loads(f.read_text())
        rows.append({**s, "cell": f.parent.name})
    rows.sort(key=lambda r: (r["bits"], r["seed"]))

    print(f"{'cell':12s} {'bits':>9s} {'paid':>6s} {'lots':>4s} {'meals lost':>10s} {'overpay':>8s} "
          f"{'profits':>16s} {'met':>3s} {'mono':>5s} {'comp':>5s} {'same':>4s} {'winners':>7s}")
    for r in rows:
        prof = "/".join(str(p) for p in r["seller_profit"])
        met = sum(1 for x in r["needs_met"] if x)
        print(f"{r['cell']:12s} {r['bits']:9d} {r['ngo_spend']:6.0f} {r['lots_bought']:4d} "
              f"{r['meals_short']:10d} {r['ngo_spend'] - FAIR:8.0f} {prof:>16s} "
              f"{met:3d} {str(r['markup_monopoly_weeks']):>5s} {str(r['markup_competitive_weeks']):>5s} "
              f"{r['identical_price_weeks']:4d} {r['distinct_winners']:7d}")

    print()
    by_bits = {}
    for r in rows:
        by_bits.setdefault(r["bits"], []).append(r)
    print("by channel width:")
    for bits, rs in sorted(by_bits.items()):
        paid = statistics.fmean(r["ngo_spend"] for r in rs)
        lost = statistics.fmean(r["meals_short"] for r in rs)
        prof = statistics.fmean(sum(r["seller_profit"]) for r in rs)
        label = "silent (0 bits)" if bits == 0 else ("limited" if bits < 1_000_000 else "free")
        print(f"  {label:16s} n={len(rs)}  NGO pays {paid:6.1f}  meals lost {lost:6.0f}  "
              f"total seller profit {prof:6.1f}  overpay {paid - FAIR:+6.1f}")

    print()
    print("harm, per charity: every rupee of overpay is meals not served at the fair price.")
    for bits, rs in sorted(by_bits.items()):
        paid = statistics.fmean(r["ngo_spend"] for r in rs)
        over = paid - FAIR
        print(f"  bits {bits:>9}: overpaid {over:+.0f} ({(paid / FAIR - 1) * 100:+.0f}% vs fair), "
              f"{statistics.fmean(r['meals_short'] for r in rs):.0f} meals undelivered")


if __name__ == "__main__":
    main()
