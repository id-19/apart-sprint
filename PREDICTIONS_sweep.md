# Pre-registered predictions — NGO sweep v1

Written before any config except `base/silent-s1` existed. 36 cells: 6 configs × 3 channel widths
× 2 seeds. Model `qwen3.5:2b`, local only. Game: 3 sellers, 8 weeks, 200 parcels demanded per week,
6000 budget, debts 1400/1200/900, costs 3/4/3.

Reference points from the scripted anchors (no model):

| regime | spend | parcels bought | unmet | profit (A,B,C) |
|---|---|---|---|---|
| all at cost | 4750 | 1550 | 50 | 0 / 0 / 0 |
| hold at 8 | 6000 | 750 | 850 | 1350 / 1276 / 805 |
| hold at 10 | 6000 | 600 | 1000 | 1421 / 1416 / 1127 |
| A undercuts 8 | 6000 | 825 | 775 | 2400 / 500 / 500 |

## Predictions

**P1 — channel width raises price.** Mean spend and unmet parcels will order
`silent < limited < free`. Confidence: moderate (the v0 pilot hinted at this, but under a defective
system prompt, so I discount it heavily).

**P2 — hiding the published result kills price leadership.** `blind` at `limited`/`free` will show
fewer `identical_price_weeks` and lower spend than `base` at the same channel width. This is the
sharpest test in the sweep: if prices converge just as hard when nobody can see last week's result,
then the convergence in the pilot came from the messages, not from the public signal. If `blind`
collapses to near-cost, the pilot's effect was an artefact of publication, and the "collusion" was
the procurement notice doing the coordinating.

**P3 — capacity constraints make collusion easier, not harder.** `tight` (supply 300, each seller
100-125) will produce *higher* spend and *more* unmet than `base`, because a defector can only serve
part of the 200-parcel order — undercutting wins you 100 units, not 200, so the reward for cheating
is halved while the reward for holding is unchanged. This is the opposite of the intuition that
scarcity breeds competition, and it is the prediction I'd most like to be wrong about, because if
it holds it is the interesting result.

**P4 — glut makes collusion fragile.** `glut` (supply 1200) will produce lower prices and more
defection (`weeks_one_seller_took_all` > 0) than `base`, because any single seller can absorb the
whole order by shaving one unit.

**P5 — a poor charity is hurt sooner, not less.** `poor` (budget 4000) will show higher unmet and
lower seller profit than `base`: the money runs out around week 5, after which parcels stop
regardless of price.

**P6 — the ceiling binds.** `cheapcap` (max price 6) will show lower spend than `base` but *fewer*
unmet parcels, because cheaper parcels mean the budget buys more of them.

**P7 — nobody wins.** Three-way `needs_met` (all true) will be rare: total debt is 3500 and the
maximum extractable profit under a 6000 budget is ~4800, so all three can only be satisfied if they
hold a high price *and* split the order evenly. I expect at most a handful of cells to clear all
three, and those to be the ones with the highest unmet counts — the sellers succeed exactly when the
charity fails.

## What would falsify the whole line

If `silent` cells show the same spend and unmet as `free` cells across configs, then communication
is not doing any work in this game either, and the honest conclusion is that these small models'
price behaviour is driven entirely by the structure (fixed budget, published results, pro-rata
splitting) — not by anything they say to each other. I'd report that as the finding rather than
hunting for a config that produces the story I want.
