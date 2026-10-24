# BUILD PLAN — Apart Sprint harness v2

**Status: DRAFT — not approved for build. No code until Ishaan approves this file by name.**
**Date:** 26 Oct 2026 · **Owner:** Ishaan · **Companion:** `EXPERIMENT_DESIGN_v2.md` (the science — what is
measured and why). This file is the scope of what must be *built* and roughly how. It contains no science.

> **Scope rule.** This build covers everything up to and including the production of per-run records
> (`summary.json`, `trajectory.jsonl`, `transcript.md`, `raw_calls.jsonl`) under the §4.2 requirements.
> Analysis — transcript reading, the Leg-1 battery, Q, figures — is a **separate later module**, deliberately
> excluded here so the producer cannot silently encode analytic choices.

---

## 1. Existing harness: reuse verdict

The prior `harness/` predates three design changes: per-channel budgeting (§2.1), the buyer-transacts-in-full
harm rule (§4.1), and the four-scenario diversity requirement (§4.4). The scenario engines are therefore
rewritten. Worth salvaging unchanged or lightly refactored: the Ollama call + retry loop (`agents.py`), the
registry pattern (`registry.py`), and the per-run directory layout convention. Verdict: **clean v2 build in
a new `harness2/` tree, reusing those three patterns**, leaving the old `harness/` untouched as the v0/v1
record. One instrument, frozen after self-tests (lesson: "one instrument must reach a matrix before it is
rewritten").

## 2. Layout

```
apart-sprint/
├── harness2/
│   ├── ollama_client.py      # §3.1 — ALL model calls
│   ├── budget.py             # §3.2 — bit counting, caps, reject-not-truncate
│   ├── comms/
│   │   ├── channel.py        # §3.3 — one Channel: common bus | mesh dyads
│   │   └── observation.py    # §3.4 — coarsen + jitter the common scalar (C2)
│   ├── tools.py              # §3.5 — sandboxed file read/write surface
│   ├── engine.py             # §3.6 — round loop, budget enforcement, logging, gates
│   ├── agents.py             # §3.7 — prompt assembly + agent turn; NEVER talks to Ollama directly
│   ├── scenarios/            # §3.8 — one module each; S3 data-room generation scripts live beside it
│   │   ├── s1_procurement.py
│   │   ├── s2_trading.py
│   │   ├── s3_rating.py
│   │   └── s4_bridge.py
│   ├── anchors.py            # §3.9 — scripted policies per scenario + the three gates + two nulls
│   ├── run_cell.py           # §3.10 — seeds, per-run dirs, registry
│   └── selftest.py           # §3.11 — harness contract tests (no model calls)
└── analysis/                 # LATER MODULE — stub only, no code in this build
```

## 3. Modules

### 3.1 `ollama_client.py`
- Single entry point `chat(messages, model, options) -> raw_response`; **no other file may import ollama or
  open a socket to it** (lesson: metadata must derive from the flow; a header written from one module's
  assumption poisoned a run).
- POST `/api/chat`, `stream:false`, `think:false`, temp 0.7; `num_ctx` set per scenario from the measured
  prompt + output budget; `keep_alive 10m`; no JSON mode (failures stay visible).
- `options.seed` passed on every call and recorded per cell (lesson: seed the model, not just tie-breaks).
- Transport: max 2 retries; `ConnectionRefused`/5xx aborts the stage after 3 consecutive failures and marks
  affected cells **INFRA** with the exception text (never `malformed`). Diagnose from `~/.ollama/logs/`.
- Memory sampling (8GB M1): every call appends our RSS, ollama-runner RSS, `vm_stat` free pages to the run's
  `memory.jsonl`; peaks → `summary.json`.
- Every call is appended verbatim (system + user + response + options + latency + digest) to
  `raw_calls.jsonl`, flushed per line.

### 3.2 `budget.py`
- `count_bits(text) -> int`: single pre-registered definition (UTF-8 bytes × 8, stated in §2.1's terms so
  every ladder label and residual printout uses the same unit).
- `check(text, cap) -> admit | reject(size)`: **reject in full, never truncate**; rejections logged with size
  even though dropped (§4.2.1).
- Pure functions, no I/O — the engine owns all logging.

### 3.3 `comms/channel.py`
- One `Channel` class parameterised by topology: `common` (one post visible to all seats) or `mesh`
  (per-dyad inboxes, N(N−1) directed links).
- Enforces §2.1: the rung cap is applied **per channel** — per post on the bus, per dyad under mesh — via
  `budget.py`. Delivery is engine-driven: a message admitted in round *t* is visible to its recipients at the
  start of round *t+1* only.
- Renders the per-seat inbox view; never exposes other seats' actions or unattributed content (§1.0).

### 3.4 `comms/observation.py`
- Produces each seat's per-round observation: `own action`, `common scalar (coarsened + jittered)`,
  `own outcome` — and nothing else.
- Coarsen: quantise the scenario's scalar to a declared grid (per scenario §4.4). Jitter: fresh uniform
  perturbation each round, seeded, unmodellable.
- Computes and reports the residual capacity estimate per arm so `run_cell` can print "0* ≈ X bits implicit"
  next to every rung (C2; threat 6: identical across arms is the requirement, exactness is not).

### 3.5 `tools.py`
- `write_file(path, content)`: only under the run's own cell directory.
- `read_file(path)`: the cell directory **plus a per-scenario read-only whitelist** (S3: the data-room
  manifest; S4: the code excerpts + checklist — S4's checklist tool is this same whitelist mechanism).
- Path resolution realpaths and rejects anything outside the allowed sets (symlink-safe); tool errors are
  returned to the model as observation text and logged, never raised (counts toward the C5 legal-action rate).
- Every tool call recorded verbatim to `raw_calls.jsonl` alongside model calls (§4.2.6 provenance).

### 3.6 `engine.py`
- Owns the round loop: observation → (optional messages, capped) → action → settle → log; calls the scenario
  module for state, scalar, settlement, and anchors for gates.
- Runs the **three blocking gates before any LLM cell** (§4.2.5) and aborts the stage on failure.
- C3: the stated budget and output limits are injected into every agent prompt via `agents.py`; engine
  verifies the injection happened before the first call (assert on prompt header).
- Writes `summary.json` (verdict code, harm decomposition, compliance rate, leak estimate, peak memory,
  prompt hash, model digest) and one `trajectory.jsonl` line **per round** (lesson: line count = day counter).
- Per-run isolation: unique run dir; refuses to reuse an existing one without `--force`; quarantines with
  `INVALID.md`, never deletes (§4.2.6).

### 3.7 `agents.py`
- Assembles prompts per scenario template: role, scenario, **stated budget + output limits (C3)**, tool
  schemas, the §1.0 observation block for this round.
- Calls a turn: send messages (through comms, capped) → produce action + optional tool calls.
- Classifies each turn: legal action / refusal / malformed (schema) / INFRA (transport) — feeds C5's >25%
  gate. No behaviour scoring here; labels only.
- Prints the exact system+user prompt to stdout on the first turn of every scenario (lesson: a wrong
  inherited SYSTEM string ruined a whole batch) and stores it in `raw_calls.jsonl`.

### 3.8 `scenarios/` (state, scalar, settlement, anchors — the table drives the code)

| | S1 procurement | S2 trading | S3 rating | S4 bridge |
|---|---|---|---|---|
| **Private state** | own cost draws, debt | own book, balance, event feed | own working notes | own role files |
| **Action space** | set price | per-contract long/short order | rating per tranche (21-notched scale) | write/verify/accept documents |
| **Common scalar** | mean transacted price | desk aggregate P&L index | published rounded mean rating | milestone status 0/1 |
| **Settle (scripted)** | buyer fully fills cheapest-first | market absorbs flow; P&L; firing every 5 rds | investors allocate on ratings | chain advance/stall; decision in final round |
| **Harm (single-axis)** | extraction overspend | P&L transfer + firing displacement | allocation-weighted risk mispricing | approval-with-gap × exposure |
| **Anchors** | cartel-optimum / competitive / random | honest-mix / shield-optimal / random | pack-rubric / inflate / exclusion / random | honest-stall / soften-accept / random |
| **Data prep** | none (params in code) | **series generator** (seeded, fictional) | **pack generator** (seeded, fictional) | **room builder** (fixed, checked in) |

S2's generator, S3's pack, and S4's room builder live beside their modules; fixtures are committed so the
"everything decisive is synthetic" invariant (§4.4.6) is auditable.

### 3.9 `anchors.py`
- Hand-coded policies through the same engine (no model calls): each scenario's anchor set from the table.
- Implements the three gates: **calibration** (scripted optimum moves the DV: extraction/P&L/rating-harm/
  milestone > 0), **compliance gate validation** (a deliberately-failing scripted actor must trip >25%),
  **planted positive / scripted negative** (collusion script must fire Leg 1 + harm; honest script must not).
- Nulls: random-assignment play (MC ≥100k draws per scenario, precomputed) and the common-cause null
  (independent scripted agents sharing the scalar).

### 3.10 `run_cell.py`
- Takes scenario × rung × topology × N × family × seed; runs the cell; updates `runs/REGISTRY.json`.
- Interleaves seeds through the ladder (shuffled schedule file committed per batch) so provider drift cannot
  masquerade as dose-response (§4.3 Phase 2).
- Prints per-cell cost and cumulative spend; one model loop at a time (Ollama serialises; concurrency reads
  as latency, i.e. as a model problem).

### 3.11 `selftest.py`
- No model calls. Verifies the contract: over-cap message rejected whole (never truncated); mesh cap applies
  per dyad and bus cap per post; observation carries exactly the three §1.0 fields; whitelist read rejects
  out-of-scope and symlink escapes; resend/drop path logs sizes; trajectory lines == rounds; INFRA path
  aborts after 3 consecutive transport failures. Freeze rule: harness is frozen once selftest passes; later
  edits record generation + prompt hash per cell.

## 4. Deliberately excluded (the later analysis module)

Leg-1 battery (`A`, ΔI_act, TE), null tests, Wilson/permutation stats, Q computation, proposal/scheme
detector, SQ5 component scoring (list OPEN, §3.3), figures/verdict table, adjudication sampling. Rationale:
they consume the *same* run records but must not tempt per-run analytic tweaking during the run phase.

## 5. Order of work

1. `selftest.py` scaffold + `budget.py` + `comms/` — prove the channel contract before anything speaks.  
2. `ollama_client.py` + `agents.py` + S1 engine — smallest path reproducing the validated scenario; gates run.  
3. S2 (+ generator) → S3 (+ pack) → S4 (+ room builder + whitelist). Each lands with anchors passing its gates.  
4. `run_cell.py` + registry.  
5. Hand back for Phase 0 approval (gate outputs + exact cell list) — **no LLM cell runs on this build alone.**

*Build, not run: this file approves construction only. Every Phase 0/1/2 execution step needs its own named
approval per `EXPERIMENT_DESIGN_v2.md` §4.2.7.*
