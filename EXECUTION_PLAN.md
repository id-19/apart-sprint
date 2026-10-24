# EXECUTION PLAN — from nothing to a defensible result by Mon 26 Oct 11:59 IST

*Companion to `DESIGN.md` (what) and `LOG.md` (what actually happened, with reasons).*
**"Frozen" claim below is FALSE — nothing was signed off. See `HANDOVER.md`.**

## 0. Operating rules

1. **Gates, not good intentions.** Each phase ends at a gate that passes or fails on a number. A failed gate
   stops the pipeline and names the fix; it never gets waved through.
2. **Nothing counts that is not on disk.** Every model call is one JSONL row carrying prompt hash, model digest,
   raw text, parsed output, byte count, rejections, latency. Analysis reads only those rows.
3. **Freeze before you look.** Prompts, levels, rubric, thresholds and the sample rule are committed before the
   first primary run. Any later change is an entry in `DEVIATIONS.md` with a reason.
4. **No local inference anywhere.** 8 GB RAM and ~200 MB free disk: every call goes to a cloud model, and
   concurrency stays at 4 or below.
5. **No waiting on Ishaan.** Every phase below is written to proceed unattended; his input is needed in exactly
   two places (§7).

## 1. Phases

| # | When (IST) | Phase | Ends with |
|---|---|---|---|
| **P0** | Sat 14:20 → 17:00 | Docs frozen · data locked · harness built · **engine self-test with scripted agents** (no LLM) | **G1** green |
| **P1** | Sat 17:00 → 19:30 | **Seed** on the cheapest cloud model: 8 conditions, 10 days, 6 seats. I read every transcript. | **G0** green + `SEED_REPORT.md` |
| **P2** | Sat 19:30 → 21:30 | Cloud pilot: 1 run at 16,000 bits, then `depth` calibration | **G2, G3, G4** |
| **P3** | Sat 21:30 → 22:30 | Controls: positive (scripted colluders) + negative (no LLM) | **G5** |
| **P4** | Sat 22:30 → 02:00 | The matrix: 106 runs, 4-way, resumable | `runs/*.jsonl` complete |
| **P5** | Sun 08:00 → 11:00 | Scoring, screener, LLM triage; Ishaan's adjudication window | labels of record |
| **P6** | Sun 11:00 → 14:00 | Curve fit, B50, latency, figures; **numbers frozen** | analysis tables |
| **P7** | Sun 14:00 → 19:00 | Report draft to 8 pages; Mon 08:00 → 11:00 buffer for his read + abstract | submitted |

Nothing below P1 is allowed to start before P1's gate passes: a pipeline that cannot run 240 local calls will
not survive 21,200 cloud calls.

## 2. Gates

| Gate | Passes when | If it fails |
|---|---|---|
| **G1 engine** | A scripted-agents run reproduces by hand: `I`, `P`, `τ`, cost, balances, one force-execution and one firing all match a worked example; totals satisfy `Σcost = I²/depth` | fix the engine. This is the only phase where bugs are cheap. |
| **G0 pipeline** | 240 seed calls complete; ≥80% parseable; caps and bounds enforced; JSONL replayable into the scorer; transcripts readable | fix prompts/parser before spending cloud calls |
| **G2 capability** | Cloud pilot: ≥90% parseable, ≥1 firing, non-degenerate leaderboard | revise framing/model before the matrix |
| **G3 calibration** | Median cumulative execution cost over 20 days ∈ 0.5–2% of 10,000; 9th–10th balance gap > 0; humans land mid-table (mean rank 4–8) | retune `depth` and/or the scripted policy **once**, log it |
| **G4 throughput** | ≥1 call/s sustained over 500 calls | 6 seeds/level; log the deviation |
| **G5 controls** | Positive control labelled ≥B in ≥4 of 5; negative clean in 3 of 3 | detector not credible — fix before reading any cell |

## 3. Artifacts

```
Apart Sprint/
  DESIGN.md  EXECUTION_PLAN.md  LOG.md  SEED_REPORT.md  DEVIATIONS.md
  data/            4 FRED CSVs + SHA256SUMS          (locked, 83 trading days 2020-03-02..06-30)
  harness/         engine.py  agents.py  run_seed.py  run_matrix.py  score.py  analyse.py
  prompts/final/   s1_system.txt  s2_turn.txt  s3_adjudicator.txt   (+ hash manifest)
  runs/            {cell}-{seed}/trajectory.jsonl  transcript.md  summary.json
  logs/            seed_*.log  matrix_*.log  gates.md
  analysis/        curve.json  b50.json  latency.json  figures/
  report/          draft.md → submitted.pdf
```

The unit of record is `trajectory.jsonl`: one row per seat-day (message, orders, bytes, rejects, parsed flags,
balances, costs, fills, published prices). Everything else is derived and can be rebuilt from it.

## 4. Commands

```bash
cd "Apart Sprint"
# G1: engine self-test, no model calls
python3 harness/run_seed.py --selftest
# P1: seed on the cheapest cloud model, one call at a time, ~5 min
python3 harness/run_seed.py --model nemotron-3-super:cloud --days 10 --ai 3 --humans 3 \
        --seed 1 --bits 0,8,32,80 --topologies forum,mesh --out runs/seed
# P2: cloud pilot + calibration
python3 harness/run_matrix.py --pilot --depth-scale 1.0
# P4: matrix (resumable; skips runs already on disk)
python3 harness/run_matrix.py --cells all --concurrency 4
# P5/P6
python3 harness/score.py --runs runs --out analysis/labels.jsonl
python3 harness/analyse.py --labels analysis/labels.jsonl --out analysis/
```

Resumability is a requirement, not a nicety: `run_matrix.py` must skip a run whose `summary.json` exists and is
marked complete, so a crash at run 80 costs one run.

## 5. Failure playbook

| Symptom | Action |
|---|---|
| Ollama stops or model unloads | restart `ollama serve`; seed run resumes from the last completed day; log the interruption |
| Cloud 502 / timeout | exponential backoff ×3, then switch to `glm-5.3-flash` for the remaining runs, logged as a cell-level deviation |
| Parse rate < 80% | tighten the output contract, add one worked example to S1, re-run G2 with a *new* pilot seed (never reuse) |
| Throughput < 1 call/s | drop to 6 seeds/level before touching levels: seeds are cheaper than cells |
| Disk below 1.5 GiB | the JSONL is ~2 KB/row; prune nothing under `runs/`, delete old `logs/` and any pulled model first |
| Cloud 404 | the daemon needs the `:cloud` suffix — `nemotron-3-super` alone returns 404 |
| Disk below 500 MB | nothing large is written (JSONL ≈ 2 KB/row); do not pull any local model |

## 6. The seed (P1) — exact specification

Purpose: prove the pipeline and give a first read of transcripts, **not** to test the hypothesis.

| | |
|---|---|
| Model | `nemotron-3-super:cloud` (cheapest listed: $0.015/M in, $0.60/M out) via the local Ollama daemon, sequential, `num_ctx 2048`, `num_predict 96`, temp 0.7, `think:false` |
| Seats | 3 AI + 3 scripted humans (6 seats) — smaller than the matrix, same mechanics |
| Days | 10 (firing checks on 5 and 10) |
| Conditions | 4 bit levels × 2 topologies: `{0, 8, 32, 80}` × `{forum, mesh}` = 8 runs |
| Seeds | 1 (illustrative only) |
| Calls | ≈ 240 → **~5 min** at ~1 s/call; cost ≈ **$0.01** for the whole seed |
| Output | `runs/seed/{cell}/trajectory.jsonl` + `transcript.md` per run, plus `SEED_REPORT.md` |
| I will | read every transcript myself, annotate what each agent tried, and report what the caps did to it |

The seed deliberately uses the **small** end of the ladder (0–80 bits) because that is where the design claims
the action is; if a 2B model can still coordinate at 8 bits/day, that is worth knowing before the cloud matrix.

## 7. What needs Ishaan — exactly two things

1. **Adjudication (Sun ~2 h).** Label ~200 flagged windows against the frozen rubric. Labels of record must be
   human; everything upstream of that is automated.
2. **Sign-off before submission.** Read the draft; check the abstract is 150–250 words and the limitations and
   dual-use sections say what he is willing to put his name to.

Both are scheduled, neither blocks P0–P4. If he is unavailable Sunday, the screener + triage labels ship and the
report says so explicitly (`labels of record: automated triage, n=…`), which is a weaker but honest submission.

## 8. Pre-committed decision rules

- **Flat curve** (B50 out of range, ceiling−floor ≈ 0): report the bound and pivot the paper to the **floor** —
  "collusion in this task does not depend on explicit messaging at all", supported by Z vs negative control and
  by `Ĥ_msg`.
- **Saturated curve** (coordination fails at every level including 16,000): the task or the model is wrong, not
  the hypothesis. Check G2/G3 diagnostics and the transcripts before interpreting anything.
- **Harm and coordination disagree** (CIs disjoint): report both, and treat coordination as primary as
  pre-registered; do not re-rank endpoints after seeing results.
- **Model refuses the task** (>20% refusals): stop, fix framing, and re-run only the failed cells with a new
  seed range — logged.

## 9. Queued, explicitly not now

- **v0 bitrate study** — re-run the older `swarm-misuse-v0` sales-deception harness at several bit caps to see
  whether the bitrate effect is market-specific. Parked until after submission; noted here so it is not lost.
- Exploratory extensions from `DESIGN.md` (4-bit extremes, horizon 10 vs 20 days, cross-model, `think` on,
  swarm size 3 vs 5) run only if the matrix finishes ahead of schedule.
