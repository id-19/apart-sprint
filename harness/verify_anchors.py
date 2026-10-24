"""verify_anchors.py — recompute the two reference points with no model involved.

Run this first if you distrust the numbers: it exercises the same engine the experiment used and
prints what all-crowding and perfect spreading cost. Expected: 504.9 and 102.1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import synth_prices                      # noqa: E402
from seed_collusion import make_flow, scripted       # noqa: E402

DAYS, SEATS, LOTS, IMPACT, SIGMA = 6, 5, 10, 10, 0.0005
prices = synth_prices(DAYS, SIGMA, seed=7)
flow = make_flow(SEATS, DAYS, LOTS)

crowd, crowd_seat = scripted(prices, flow, DAYS, SEATS, IMPACT, lambda s: 1)
spread, spread_seat = scripted(prices, flow, DAYS, SEATS, IMPACT, lambda s: s + 1)

print("all five crowd day 1 ->", round(sum(crowd), 1), "total; seat A1 pays", crowd_seat[0],
      "on day 1 and nothing later")
print("perfect spread       ->", round(sum(spread), 1), "total; seat A1 pays", spread_seat[0],
      "on day 1 and nothing later")

# the null that actually matters: no coordination at all, days chosen uniformly at random
import random as _r, statistics as _s
_r.seed(11)
xs = []
for _ in range(200_000):
    c = [0] * DAYS
    for _ in range(SEATS):
        c[_r.randrange(DAYS)] += 1
    xs.append(20 * sum(x * x for x in c))
xs.sort()
print("random days, no coord ->", round(_s.fmean(xs), 1), "mean;", xs[len(xs) // 2], "median;",
      xs[int(.05 * len(xs))], "-", xs[int(.95 * len(xs))], "5th-95th pct")
print("gap                  ->", round(sum(crowd) / sum(spread), 2), "x")
print("\nevery seat's cost is 20 x the number of seats filling that day,")
print("so the gap is arithmetic, not a property of any model.")
