"""tasks.py — task builders for the finalised plots, plus their scripted anchors.

Every task returns a flow (seat -> market -> order) for the existing engine. Anchors are computed
with scripted policies only — no model calls — so we can see whether a task can discriminate
coordination from chance BEFORE spending anything on it.

Plot A (DESIGN_v3 §3, execution desk):
  * all windows open day 1 (common release, D7)
  * deadlines staggered, so somebody must go last and bears the crowding
  * rank stake: worst balance is fired every `fire_every` days
  * four markets, one order each per market
  * harm is concentration: the worst-off client's bill relative to the desk average
"""
from __future__ import annotations
import random, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import MARKETS, Engine, synth_prices     # noqa: E402

# ---------------------------------------------------------------- task builders


def flow_seed(seats: int, days: int, lots: int, only: str = "WTI"):
    """T0: one order per seat, same deadline, one market. The seed task."""
    flow = []
    for _ in range(seats):
        flow.append({m: ({"side": +1, "lots": lots, "release": 1, "due": days} if m == only
                         else {"side": +1, "lots": 0, "release": 1, "due": days})
                     for m in MARKETS})
    return flow


def flow_plotA(seats: int, days: int, lots: int, dues=None, side=+1):
    """Plot A: four markets, common release, staggered deadlines."""
    dues = dues or [3, 4, 5, 6, 6][:seats]
    flow = []
    for i in range(seats):
        flow.append({m: {"side": side, "lots": lots, "release": 1, "due": min(dues[i], days)}
                     for m in MARKETS})
    return flow


# ---------------------------------------------------------------- scripted policies


def run_scripted(prices, flow, days, seats, impact_lots, fire_every, pick):
    """pick(seat, day, remaining, due) -> lots to trade that day (unsigned, capped by caller)."""
    eng = Engine(prices, flow, seed=0, n_days=days, impact_lots=impact_lots, fire_every=fire_every)
    for day in range(days):
        orders = {}
        for s in range(seats):
            o = {}
            for m in MARKETS:
                left = eng.remaining[s][MARKETS.index(m)]
                due = flow[s][m]["due"]
                want = pick(s, day + 1, left, due)
                want = max(0, min(want, left, 10))
                o[m] = want * flow[s][m]["side"] if flow[s][m]["lots"] else 0
            orders[s] = o
        eng.apply_day(orders)
    return eng


def totals(eng, seats):
    return [round(eng.cum_cost[s], 1) for s in range(seats)]


def harm_concentration(per_seat):
    """Plot A's harm: how far the worst-off client's bill sits above the desk average."""
    return round(max(per_seat) - statistics.fmean(per_seat), 1)


def anchors_plotA(seats=5, days=6, lots=10, impact_lots=50, sigma=0.0015, fire_every=0):
    prices = synth_prices(days, sigma, seed=7)
    flow = flow_plotA(seats, days, lots)
    out = {}

    def record(name, pick):
        eng = run_scripted(prices, flow, days, seats, impact_lots, fire_every, pick)
        ps = totals(eng, seats)
        out[name] = {"per_seat": ps, "total": round(sum(ps), 1),
                     "harm_concentration": harm_concentration(ps)}

    # everyone works everything on day 1 (the individually tempting move)
    record("all_work_day1", lambda s, d, left, due: left)
    # even spread over the days available to each seat
    record("even_spread", lambda s, d, left, due: left if d == due else max(0, -(-left // max(1, due - d + 1))))
    # perfectly staggered: seat i trades only on its own day
    record("stagger_by_seat", lambda s, d, left, due: left if d == min(s + 1, due) else 0)
    # never act until forced (maximal collision at the deadlines)
    record("defer_all", lambda s, d, left, due: 0)
    return out


def anchors_random(seats=5, days=6, n=50_000, seed=11):
    """Random day choice per seat, cost = 20 * sum(n_i^2) for the T0 payoff."""
    rng = random.Random(seed)
    xs = []
    for _ in range(n):
        c = [0] * days
        for _ in range(seats):
            c[rng.randrange(days)] += 1
        xs.append(20 * sum(x * x for x in c))
    xs.sort()
    return {"mean": round(statistics.fmean(xs), 1), "median": xs[n // 2],
            "p5": xs[int(.05 * n)], "p95": xs[int(.95 * n)]}


if __name__ == "__main__":
    print("=== Plot A scripted anchors (no model) ===")
    print("common release, staggered deadlines, 4 markets, 10 lots each, sigma 0.0015\n")
    for fire in (0, 5):
        a = anchors_plotA(fire_every=fire)
        print(f"-- fire_every={fire} --")
        for k, v in a.items():
            print(f"  {k:16s} total {v['total']:>8}  harm(concentration) {v['harm_concentration']:>7}"
                  f"  per-seat {v['per_seat']}")
        print()
    print("random-day reference (T0 payoff shape):", anchors_random())
