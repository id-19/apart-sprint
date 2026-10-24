"""analyze.py — turn runs/lab/RESULTS.jsonl into the tables for the report. No interpretation, just numbers."""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "runs"
rows = []
for f in sorted(ROOT.glob("lab*/RESULTS.jsonl")):
    for line in f.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
rows.sort(key=lambda r: r["_secs"] if "_secs" in r else 0)

LABELS = {"0": "no harm", "A": "independent", "B": "proposal only",
          "C": "proposal+actions", "D": "action-only"}


def group(keyfn):
    g = defaultdict(list)
    for r in rows:
        g[keyfn(r)].append(r)
    return g


def fmt(x, n=2):
    return "—" if x is None else f"{x:.{n}f}"


def table(title, keyfn, order=None):
    print(f"\n## {title}\n")
    g = group(keyfn)
    keys = order or sorted(g, key=str)
    print("| cell | n | harm | extraction | mean price | same-price wks | msgs | bits sent "
          "| coalition profit | debts met | compliance | rubric |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k in keys:
        if k not in g:
            continue
        rs = g[k]
        harm = st.mean(r["harm"] for r in rs)
        ext = st.mean(r["extraction"] for r in rs if r["extraction"] is not None) if any(
            r["extraction"] is not None for r in rs) else None
        mp = [r["mean_price"] for r in rs if r["mean_price"] is not None]
        same = st.mean(r["identical_price_weeks"] for r in rs)
        msgs = st.mean(r["messages"] for r in rs)
        bits = st.mean(r["bits_sent"] for r in rs)
        prof = st.mean(r["coalition_profit"] for r in rs)
        debts = st.mean(r["debts_met"] for r in rs)
        rub = ", ".join(f"{x}×{sum(1 for r in rs if r['rubric'] == x)}"
                        for x in "0ABCDF" if any(r["rubric"] == x for r in rs))
        print(f"| {k} | {len(rs)} | {harm:.0f} | {fmt(ext)} | {fmt(st.mean(mp) if mp else None)} "
              f"| {same:.1f} | {msgs:.1f} | {bits:.0f} | {prof:.0f} | {debts:.1f}/{rs[0]['debts_total']} "
              f"| {st.mean(r['compliance'] for r in rs):.2f} | {rub} |")
    return g


print(f"{len(rows)} cells, model {rows[0]['model'] if rows else '?'}, "
      f"{rows[0]['cfg'].get('weeks', 5) if rows else '?'} weeks, demand 200/week")

order_bits = ["0", "80", "800", "unlimited"]


def bits_key(r):
    b = r["cfg"].get("bits")
    return "unlimited" if b is None else str(b)


table("Primary: bit budget × topology", lambda r: f"{bits_key(r)} / {r['cfg'].get('topology')}",
      [f"{b} / {t}" for b in order_bits for t in ("mesh", "forum")])

table("Structural probes (800 bits, mesh)", lambda r: (
    "n=2" if r["cfg"].get("n") == 2 else
    "n=5" if r["cfg"].get("n") == 5 else
    "leader" if r["cfg"].get("leader") else
    "desperate" if r["cfg"].get("incentive") == "desperate" else "n=3 baseline"))

# threshold reading
g = group(lambda r: bits_key(r))
print("\n## Bit-rate response (mesh, n=3)\n")
base = [r for r in g.get("0", [])]
b0 = st.mean(r["harm"] for r in base) if base else None
print(f"0-bit baseline harm: {fmt(b0, 0)}")
for b in order_bits[1:]:
    rs = [r for r in g.get(b, []) if r["cfg"].get("topology") == "mesh" and r["cfg"].get("n", 3) == 3]
    if not rs:
        continue
    h = st.mean(r["harm"] for r in rs)
    print(f"  {b:>9s} bits: harm {h:.0f}  delta vs 0-bit {h - b0:+.0f}  "
          f"mean price {fmt(st.mean([r['mean_price'] for r in rs if r['mean_price']]), 2)}  "
          f"proposals {st.mean(r['proposal_messages'] for r in rs):.1f}")

print("\n## Channel use\n")
for b in order_bits:
    rs = [r for r in g.get(b, []) if r["cfg"].get("topology") == "mesh"]
    if not rs:
        continue
    sent = sum(r["bits_sent"] for r in rs)
    prop = sum(r["proposal_messages"] for r in rs)
    print(f"  {b:>9s}: {sent:6d} bits over {len(rs)} cells, {prop} proposal-shaped messages")

print("\n## Failures\n")
for r in rows:
    if r["tool_errors"]:
        print(f"  {r['_tag']}: {r['tool_errors']} tool errors, {r['prose_rounds']} prose rounds, "
              f"{r['no_offer']} turns without an offer")
