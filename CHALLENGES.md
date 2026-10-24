# CHALLENGES.md — build log for harness2 v1 (S1 cell)

Everything below is a real problem hit during the dummy-tested build and either fixed in place (with the commit) or still open at the bottom. Kept short; the point is the *shape* of the failure and the fix.

## 1. Off-by-one budget: nominal ladder vs byte divisibility
- **Problem.** Test assumed `cap=500` admits a 500-bit message, but `check` counts *bytes* then multiplies by 8 — a cap of 500 admits floor(500/8)=62 bytes = 496 bits. 500 is not byte-divisible.
- **Fix.** Ladder is *nominal* {0\*, 512, 1024, 16384} bits = {0\*, 64, 128, 2048} bytes. Byte-boundary arithmetic is a harness detail, not a science constant. Test now asserts 496 is admitted, 512 is rejected, and the exact divisor is recorded per cell. `test_budget.py` 7/7.

## 2. F-string syntax error nested quotes in common-bus rejection
- **Problem.** `f"bus post\">{self.cap}b"` — a literal `>` then a quote ended the string. Module wouldn't even import.
- **Fix.** Split the detail string: `f"bus post>{self.cap}b" if self.cap else "bus post"`. Pyright caught it immediately; verified by re-running the channel suite.

## 3. Settle crashed when a seat never set a price
- **Problem.** The failing-actor gate (deliberately never produces `PRICE:`) left `world.prices` empty, and `settle()` did `self.prices[s]` → `KeyError: 'A'`.
- **Fix.** `settle` now treats an unpriced seat as *skipped* (withholding): the buyer fills cheapest-first only among seats WITH prices; the unpriced seat's share counts toward `withholding`. This is also the honest semantic for a malformed turn — it doesn't transact. `test_s1.py` 6/6.

## 4. Honest anchor was indistinguishable from collusion
- **Problem.** The controls gate failed: planted-cartel hurt (harm=72) but honest hurt too (harm=18). Cause: honest anchor priced at 10 against a competitive price of 9 — every seller above competitive price produces *some* extraction, so the "planted vs honest" split never fired.
- **Fix.** Honest anchor must price AT the competitive price (9) => extraction exactly 0. Now cartel=72, honest=0, `test_controls_split_planted_from_honest` passes. This is a design point, not just a code fix: **the controls gate only works if the honest baseline produces zero DV.**

## 5. record.py INFRA came from the wrong channel
- **Problem.** Subagent's `finalise()` flipped the cell to INFRA if *any logged message* had verdict "infra" (`_deadmalformed_counts > 0`). But INFRA is a *turn* status (transport collapse), not a message disposition — a malformed or even an "infra"-tagged message must not invalidate the cell.
- **Fix.** Removed `_deadmalformed_counts` from the verdict rule; INFRA comes only from `log_round(verdict="infra")`. Renamed default verdict "VALID"→"SIGNAL" to match the design's three labels. `_infra` initialised in `__init__` (was read cold).

## 6. Subagent's own test didn't match its module's contract
- **Problem.** Its test expected 3 trajectory lines (one per seat-round); the module wrote one line per *round* (2). It also used a pytest `tmp_path` fixture the suite doesn't have.
- **Fix.** Rewrote the test to assert the module's real contract (per-round lines, compliance rate 4 seat-rounds), plain `tempfile`. The module itself was already correct to spec — only its test was wrong. `test_record.py` 2/2.

## 7. Module-resolution / import-root churn after moving tests into `tests/`
- **Problem.** Moving 5 test files into `tests/` broke `sys.path.insert(0, os.path.dirname(__file__))` (now points at `tests/`).
- **Fix.** All tests use `os.path.dirname(os.path.dirname(__file__))` (the `harness2/` root). One-liner per file, suite rerun.

## 8. Gate engines polluted the real run dir
- **Problem.** `Engine.run_gates()` spins up throwaway `Engine`s for calibration/compliance/controls; they wrote `raw_calls.jsonl` etc. into the same `run_dir` as the real cell.
- **Fix.** Gate engines run in a `_gate`/`_gates` subdirectory. Records from the *real* cell are now cleanly separated from gate scratch.

## Still open / next
- `granite4.2:3b` was not pulled on this Mac; first real mini-run used `qwen3.5:2b` (3.1 GB, already installed). Swap model by flag when granite is available.
- The recorder is *not yet wired into* `engine.run()` per-turn (recorder only receives `finalise`). Wiring `log_round` per seat per round is the next atomic step before analysis.
- Mesh + 0* rung cells need cell runs; only `common` × `1024` validated end-to-end with a scripted transport.
- S2/S3/S4 scenario modules unbuilt (by design — S1 first).
- Memory sampling is per-call; a proper peak tracker is next so a run is killed on a real peak, not post-hoc.
