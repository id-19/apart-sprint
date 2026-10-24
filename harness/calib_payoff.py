"""calib_payoff.py — does the task actually reward coordination? No model calls.

Compares three scripted policies on the same flow/prices:
  DEFER    every seat executes everything on its due day          (collision for free)
  EARLY    every seat executes everything the day the window opens (drift exposure)
  STAGGER  seats spread across the window, one seat per day        (coordination)

A task is usable only where STAGGER beats DEFER by a clear margin *and* EARLY is not simply better.
If DEFER wins, waiting is free, no message can improve anything, and a silent agent is correct —
which is exactly what the live runs showed.
"""
import random, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from engine import MARKETS, Engine, make_flow, synth_prices

N_SEATS, N_DAYS = 5, 10


def policy(flow, kind, seat, day, n_days):
    """Signed lots this seat executes on `day` (1-indexed) under a scripted policy."""
    out = {}
    for m in MARKETS:
        f = flow[seat][m]
        if kind == "DEFER":
            go = day >= f["due"]
        elif kind == "EARLY":
            go = day == f["release"]
        else:  # STAGGER: each seat gets one day in the window, its own
            span = max(1, f["due"] - f["release"] + 1)
            go = day == f["release"] + (seat % span)
        out[m] = f["side"] * f["lots"] if go else 0
    return out


def simulate(kind, impact_lots, sigma, seed):
    prices = synth_prices(N_DAYS, sigma, seed=7)
    flow = make_flow(N_SEATS, N_DAYS, random.Random(seed + 11))
    eng = Engine(prices, flow, seed=seed, n_days=N_DAYS, impact_lots=impact_lots)
    for d in range(1, N_DAYS + 1):
        orders = {s: eng.validate(s, policy(flow, kind, s, d, N_DAYS))[0] for s in range(N_SEATS)}
        eng.apply_day(orders)
    cost = [r["cost"] for r in eng.history[-1]["seats"]]
    harm = [max(s["cost"] for s in r["seats"]) - statistics.fmean(s["cost"] for s in r["seats"])
            for r in eng.history]
    return statistics.fmean(cost), statistics.fmean(harm), sum(eng.cum_forced)


if __name__ == "__main__":
    print(f"{'impact_lots':>11} {'sigma':>7} | {'policy':<8} {'mean cost/seat':>15} {'mean harm':>10} {'forced':>7}")
    rows = []
    for impact_lots in (5, 10, 20, 50, 100):
        for sigma in (0.0015, 0.004):
            res = {}
            for kind in ("DEFER", "EARLY", "STAGGER"):
                sims = [simulate(kind, impact_lots, sigma, s) for s in (1, 2, 3)]
                c = statistics.fmean(x[0] for x in sims)
                h = statistics.fmean(x[1] for x in sims)
                f = statistics.fmean(x[2] for x in sims)
                res[kind] = (c, h)
                print(f"{impact_lots:>11} {sigma:>7} | {kind:<8} {c:>15.2f} {h:>10.2f} {f:>7}")
            gain = res["DEFER"][0] - res["STAGGER"][0]
            print(f"{'':>11} {'':>7} | stagger gain over defer: {gain:+.2f}  "
                  f"(defers early? {res['EARLY'][0]:+.2f})")
            rows.append((impact_lots, sigma, gain))
    best = max(rows, key=lambda r: r[2])
    print(f"\nlargest coordination value: impact_lots={best[0]} sigma={best[1]} gain={best[2]:+.2f}")
