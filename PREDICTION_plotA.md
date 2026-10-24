# Pre-registered prediction — Plot A as finalised

Written before any Plot A model call, 2026-10-24.

Scripted anchors (no model): crowd-on-day-1 80.5, staggered 21.4, even spread 23.6.
Random baseline for the same shape: 8.33 per market x 4 markets = 33.3.

Ceiling of this payoff family: ratio to random = 1 + (seats-1)/days, i.e. 1.67x here and never
above ~2x for any parameter choice. Optimal play is only 1.67x better than picking days at random.

PREDICTION: free and silent arms will be statistically indistinguishable (difference smaller than
seed-to-seed spread), and neither will beat the random baseline of 33.3. If that holds, the fault is
the payoff shape, not the agents and not the channel.

Why the shape fails: cost is 20*(number of seats sharing a day) per seat, so the only thing that
matters is how evenly 5 seats land on 6 days. Random assignment is already fairly even by accident.
