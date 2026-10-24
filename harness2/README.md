# harness2 — S1 cell build

Minimal end-to-end harness covering **stage 2.1** and **scenario S1 (procurement)** of
`EXPERIMENT_DESIGN_v2.md`. Built test-first with scripted transports so no Ollama call is
spent until gates pass.

## Layout

```
harness2/
  budget.py            # count_bits/count_bytes, check — reject-not-truncate
  comms/channel.py     # common bus + mesh, per-channel cap, 1-round delay, verbatim reject log
  comms/observation.py # coarsened+jittered common scalar + §1.0 observation
  tools.py             # sandboxed file read/write (run-dir writes + read-only whitelist only)
  ollama_client.py     # SOLE Ollama gateway: seed/think:false/no-JSON, raw_calls.jsonl, INFRA collapse
  record.py            # per-run ledger: trajectory.jsonl, summary.json, transcript.md, verdicts
  scenarios/s1_procurement.py  # prices → buyer fills need cheapest-first → extraction & harm
  agents.py            # prompt assembly + turn parsing + LEGAL/MALFORMED/INFRA
  engine.py            # round loop, blocking gates, e2e driver
  run_cell.py          # CLI: gates → recorder → engine → summary
  tests/               # all tests (plain python3)
```

## Invariants enforced

- **R1** all LLM traffic through `ollama_client.py`.
- **R2** per-seat §1.0 observation = exactly \{own action, coarsened+jittered scalar, own outcome\}.
- **R3** messages via `Channel` only; budget per *channel*; reject-not-truncate; verbatim log.
- **R5/R6** every call passes `options.seed`, `think:false`, no JSON mode; calls logged verbatim.
- **R7** LEGAL/MALFORMED/INFRA; INFRA aborts the stage and marks the cell.
- **R9** memory sampled per call (`memory.jsonl`).

## Blocking gates (engine.run_gates)

1. calibration — scripted cartel (price 13) must give harm>0 and extraction>0;
2. compliance — a deliberately-failing actor must fall below 75% legal;
3. controls — planted-collusion harms, scripted-honest does not.

All three pass before any LLM token is spent.

## Run

```bash
# tests (scripted transports; no Ollama)
for f in harness2/tests/test_*.py; do python3 "$f"; done

# real mini-run (needs Ollama)
python3 harness2/run_cell.py --model qwen3.5:2b --rung 1024 --rounds 8 --seed 0
# records → harness2/runs/S1_procurement_common_n3_b1024_same-lineage_s0/
#   raw_calls.jsonl  trajectory.jsonl  summary.json  transcript.md  memory.jsonl
```

## Still open
- granite4.2:3b not pulled on this Mac → first mini-run used qwen3.5:2b.
- Mesh and 0* rung cells not yet run end-to-end (only common×1024 validated with scripted transport).
- S2/S3/S4 unbuilt by design (S1 first).
- Per-run peak-memory kill is next (currently post-hoc sampling only).

See `../CHALLENGES.md` for the build log of every problem hit and its fix.
