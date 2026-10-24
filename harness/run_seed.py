"""run_seed.py — driver for the local seed (P1) and the engine self-test (G1).

    python3 harness/run_seed.py --selftest
    python3 harness/run_seed.py --model qwen3.5:2b --days 10 --ai 3 --humans 3 \
            --seed 1 --bits 0,8,32,80 --topologies forum,mesh --out runs/seed

Writes, per run: trajectory.jsonl (one row per seat-day), transcript.md, summary.json.
Never parallel: one model call at a time, so the laptop stays usable.
"""
from __future__ import annotations
import argparse, json, math, random, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine import (MARKETS, Engine, make_flow, load_prices, coordination,
                    same_day_coincidence, B0)
from agents import (SYSTEM, ScriptedHuman, chat, parse_reply, route, turn_prompt)


def build_flow(n_seats, n_days, seed):
    return make_flow(n_seats, n_days, random.Random(seed))


def run_one(model, n_days, n_ai, n_humans, seed, bits, topology, out_dir, verbose=True):
    n_seats = n_ai + n_humans
    names = [f"A{i+1}" for i in range(n_ai)] + [f"H{i+1}" for i in range(n_humans)]
    prices = load_prices(Path(__file__).resolve().parent.parent / "data", n_days)
    eng = Engine(prices, build_flow(n_seats, n_days, seed + 7), seed=seed, n_days=n_days)
    humans = [ScriptedHuman(names[n_ai + i], n_days) for i in range(n_humans)]
    ai_seats = list(range(n_ai))
    sent_to.clear()
    inbox = {s: [] for s in ai_seats}        # delivered next day
    hist = {s: [] for s in ai_seats}
    traj_path = out_dir / "trajectory.jsonl"
    tpath = out_dir / "transcript.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    traj_path.write_text("")
    tpath.write_text(f"# Transcript — {out_dir.name}\n\nmodel `{model}` · {n_seats} seats "
                     f"({n_ai} AI + {n_humans} human) · {n_days} days · {bits} bits/day · "
                     f"{topology} · seed {seed}\n\n")
    stats = {"calls": 0, "malformed": 0, "over_cap": 0, "latency": [], "bytes": [],
             "prompt_chars": []}
    t_start = time.time()

    for day in range(n_days):
        obs_all = {s: eng.observe(s) for s in range(n_seats)}
        for s in range(n_seats):
            obs_all[s]["_names"] = names
        msgs_today = {s: None for s in range(n_seats)}
        orders = {}

        # --- communication + AI actions -----------------------------------
        for s in ai_seats:
            peers = [names[j] for j in ai_seats if j != s]
            h = ("Your last 3 days: " + "; ".join(hist[s][-3:])) if hist[s] else ""
            prompt = turn_prompt(obs_all[s], names[s], peers, inbox[s], bits, topology,
                                 n_days, h)
            stats["prompt_chars"].append(len(prompt))
            text, secs, _raw = chat(model, SYSTEM, prompt)
            stats["calls"] += 1
            stats["latency"].append(round(secs, 2))
            parsed, flags = parse_reply(text)
            sent_to[s] = parsed["to"]
            kept, rflags = route(parsed["message"], bits)
            flags += rflags
            if "malformed" in flags:
                stats["malformed"] += 1
            if "over_cap_drop" in flags:
                stats["over_cap"] += 1
            stats["bytes"].append(len(kept.encode()))
            msgs_today[s] = kept if kept else None
            v, vflags = eng.validate(s, parsed["orders"])
            orders[s] = v
            if verbose:
                m = (kept[:40] + "…") if kept and len(kept) > 40 else (kept or "")
                print(f"  d{day+1:02d} {names[s]} {secs:4.1f}s msg=[{m}] "
                      f"q={v} flags={flags+vflags}", flush=True)
            od = ",".join(f"{m}{v[m]:+d}" for m in MARKETS if v[m]) or "no orders"
            hist[s].append(f"d{day+1} sent {len(kept)}B, {od}")

        # --- scripted humans ----------------------------------------------
        for i in range(n_humans):
            s = n_ai + i
            orders[s] = eng.validate(s, humans[i].act(obs_all[s]))[0]

        # --- resolve the day ----------------------------------------------
        rec = eng.apply_day(orders)
        fired = eng.firing_check()
        rec["messages"] = {names[s]: msgs_today[s] for s in ai_seats}
        rec["topology"], rec["bits"] = topology, bits
        with open(traj_path, "a") as f:
            f.write(json.dumps(rec) + "\n")

        # --- deliver to tomorrow's inbox (one day of context, never accumulating)
        for s in ai_seats:
            if topology == "forum":
                inbox[s] = [f"{names[j]}: {msgs_today[j]}" for j in ai_seats
                            if j != s and msgs_today[j]]
            else:  # mesh: only what was addressed to me by name
                inbox[s] = [f"{names[j]}: {msgs_today[j]}" for j in ai_seats
                            if j != s and msgs_today[j] and names[s] in sent_to.get(j, [])]

        # transcript
        with open(tpath, "a") as f:
            f.write(f"\n## Day {rec['day']} — {rec['date']}"
                    + (f" — FIRED {names[fired['seat']]}" if fired else "") + "\n")
            for s in range(n_seats):
                r = rec["seats"][s]
                who = names[s] + (" (AI)" if s < n_ai else " (human)")
                f.write(f"- **{who}** bal {r['balance']:.0f} cost {r['cost']:+.2f} "
                        f"q={ {m: r['q'][m] for m in MARKETS if r['q'][m]} }"
                        + (" FORCED" if any(r["forced"].values()) else "") + "\n")
            for s in ai_seats:
                f.write(f"  - msg {names[s]}: {msgs_today[s]!r}\n")
            f.write(f"  - flow I={ {m: rec['I'][m] for m in MARKETS} } "
                    f"P_pub={ {m: round(rec['P_pub'][m],2) for m in MARKETS} }\n")

    # --- summary -----------------------------------------------------------
    bal = [r["balance"] for r in eng.history[-1]["seats"]]
    a, n_pairs = coordination(eng.history, ai_seats)
    sdc = same_day_coincidence(eng.history, ai_seats)
    human_fired = sum(1 for s in range(n_ai, n_seats) if eng.fired[s])
    ai_fired = sum(1 for s in range(n_ai) if eng.fired[s])
    ident = max(abs(r["cost_identity"]["sum_impact"] - r["cost_identity"]["I2_over_depth"])
                for r in eng.history)
    summary = {
        "model": model, "days": n_days, "ai": n_ai, "humans": n_humans, "seed": seed,
        "bits": bits, "topology": topology,
        "calls": stats["calls"], "malformed": stats["malformed"],
        "over_cap_drops": stats["over_cap"],
        "parse_rate": round(1 - stats["malformed"] / max(1, stats["calls"]), 3),
        "msg_bytes_total": sum(stats["bytes"]),
        "msg_bytes_mean": round(statistics.fmean(stats["bytes"]), 2) if stats["bytes"] else 0,
        "latency_mean": round(statistics.fmean(stats["latency"]), 2) if stats["latency"] else 0,
        "prompt_chars_mean": round(statistics.fmean(stats["prompt_chars"])) if stats["prompt_chars"] else 0,
        "A": None if math.isnan(a) else round(a, 4), "A_obs": n_pairs,
        "same_day": None if math.isnan(sdc) else round(sdc, 4),
        "human_fired": human_fired, "ai_fired": ai_fired,
        "firings": [{"day": f["day"], "seat": names[f["seat"]]} for f in
                    ({"day": d, "seat": s} for s in range(n_seats) for d in eng.fired[s])],
        "final_balances": {names[s]: round(bal[s], 1) for s in range(n_seats)},
        "cost_identity_max_abs_err": round(ident, 12),
        "wall_seconds": round(time.time() - t_start, 1),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


# seat -> names this seat addressed today (mesh delivery)
sent_to: dict[int, list[str]] = {}


def selftest():
    """G1: scripted agents only. Checks the identity, force-execution, firing, bounds."""
    print("G1 engine self-test (no model calls)\n")
    prices = load_prices(Path(__file__).resolve().parent.parent / "data", 10)
    flow = make_flow(6, 10, random.Random(1))
    eng = Engine(prices, flow, seed=1, n_days=10)
    humans = [ScriptedHuman(f"H{i+1}", 10) for i in range(6)]
    orders_hist = []
    for day in range(10):
        orders = {s: eng.validate(s, humans[s].act(eng.observe(s)))[0] for s in range(6)}
        orders_hist.append(orders)
        rec = eng.apply_day(orders)
        f = eng.firing_check()
        if f:
            print(f"  firing day {f['day']}: seat {f['seat']} at {f['balance_before']:.1f}")
        assert abs(rec["cost_identity"]["sum_impact"]
                   - rec["cost_identity"]["I2_over_depth"]) < 1e-6
        for s in range(6):
            assert min(rec["seats"][s]["remaining"].values()) >= 0
    # worked example for day 1
    r = eng.history[0]
    print("\n  worked example, day 1:")
    tot0 = 0.0
    for i, m in enumerate(MARKETS):
        q = r["seats"][0]["q"][m]
        exp = q * (r["P_exact"][m] - r["H"][m]) + 0.1 * abs(q) if q else 0.0
        tot0 += exp
        print(f"   {m:6} H={r['H'][m]:7.2f} I={r['I'][m]:+4d} depth={r['depth'][m]:8.2f} "
              f"P={r['P_exact'][m]:7.2f} P_pub={r['P_pub'][m]:7.2f} q0={q:+3d} cost={exp:+.3f}")
    print(f"   seat0 day-1 total {tot0:+.3f} vs recorded {r['seats'][0]['cost']:+.3f}")
    forced = sum(1 for rec in eng.history for s in rec["seats"] if any(s["forced"].values()))
    print(f"\n  forced executions in the scripted run: {forced} (scripted policy never leaves flow unfilled)")

    # force-execution path, tested directly: nobody trades, so every due day must force
    eng2 = Engine(prices, make_flow(3, 5, random.Random(9)), seed=9, n_days=5)
    for _ in range(5):
        eng2.apply_day({s: {m: 0 for m in MARKETS} for s in range(3)})
    fe = sum(1 for rec in eng2.history for s in rec["seats"] if any(s["forced"].values()))
    zero_left = all(min(rec["seats"][s]["remaining"].values()) == 0
                    for rec in eng2.history[-1:] for s in range(3))
    print(f"  force-execution path: {fe} seat-days forced, all flow cleared by day 5: {zero_left}")
    assert fe > 0 and zero_left, "force-execution path broken"
    print(f"  identity max abs error: "
          f"{max(abs(x['cost_identity']['sum_impact'] - x['cost_identity']['I2_over_depth']) for x in eng.history):.2e}")
    print(f"  coordination A (scripted, all): {coordination(eng.history, list(range(6)))[0]:.3f}")
    ok = (fe > 0) and (zero_left) and max(
        abs(x["cost_identity"]["sum_impact"] - x["cost_identity"]["I2_over_depth"])
        for x in eng.history) < 1e-9
    print("\n  G1 PASS — identity exact, firing works, force-execution works, bounds hold"
          if ok else "\n  G1 FAIL")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--model", default="qwen3.5:2b")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--ai", type=int, default=3)
    ap.add_argument("--humans", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bits", default="0,8,32,80")
    ap.add_argument("--topologies", default="forum,mesh")
    ap.add_argument("--out", default="runs/seed")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    root = Path(__file__).resolve().parent.parent
    out = root / args.out
    bits_list = [int(b) for b in args.bits.split(",")]
    summaries = []
    for topo in args.topologies.split(","):
        for bits in bits_list:
            cell = f"{topo}-b{bits}"
            if (out / cell / "summary.json").exists():      # resumable
                print(f"\n=== {cell} === (already complete, skipping)", flush=True)
                summaries.append(json.loads((out / cell / "summary.json").read_text()))
                continue
            print(f"\n=== {cell} ===", flush=True)
            s = run_one(args.model, args.days, args.ai, args.humans, args.seed, bits,
                        topo, out / cell)
            summaries.append(s)
            print(f"  -> parse {s['parse_rate']:.2f} A={s['A']} "
                  f"human_fired={s['human_fired']} bytes={s['msg_bytes_total']} "
                  f"{s['wall_seconds']}s", flush=True)
    (out / "all_summaries.json").write_text(json.dumps(summaries, indent=2))
    print("\n" + json.dumps([{k: s[k] for k in
                             ("bits", "topology", "A", "same_day", "human_fired",
                              "parse_rate", "msg_bytes_total", "wall_seconds")}
                            for s in summaries], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
