# harness2 — bitrate × collusion

One shared engine. Four scenario modules. Every model call, message, tool call,
observation, settlement, and thinking trace is written to an append-only cell
directory. No model call is made by the plan or selfcheck paths.

## Commands

```bash
python3 -m harness2.entry plan                 # 310-cell schedule + hashes
python3 -m harness2.entry selfcheck            # config + scripted anchors, no model
python3 -m harness2.entry dummy --scenario s1  # scripted end-to-end cells, no model
python3 -m harness2.entry run --approve runs/plan.json --scenario s1 --limit 1
python3 -m harness2.entry analyze --runs runs
```

`run` refuses a stale plan, a config whose schedule hash changed, or a model
still marked `TBD`. A rerun of an existing cell gets a new `_aN` directory; the
previous attempt is never overwritten.

## Layout

```
harness2/
  entry.py          CLI: plan · selfcheck · dummy · run · analyze
  config.py         axes, seats, cells, deterministic schedule, hashes, run dirs
  engine.py         cycle loop, six exchanges, terminal-only last exchange, verdicts
  model.py          sole Ollama gateway; native tools; thinking; raw call log
  tools.py          private files, read-only HTML corpus, local search_web, comms
  comms/channel.py  transferable byte allowance; forum + DMs; reject whole
  comms/observation.py  coarsened + jittered public scalar
  record.py         append-only raw_calls/messages/trajectory/settlement/live_flags
  scenario.py       scenario protocol
  scenarios/s1.py   procurement pricing desks
  scenarios/s2.py   trading desks on five lobster order books
  scenarios/s3.py   bond rating desks and placement fees
  scenarios/s4.py   bridge package / checker / reviewer chain
  data/docs/s1..s4  read-only in-world HTML corpus
  vendor/lobster/   pinned MIT order-book engine (S2 only)
  tests/test_core.py, tests/test_config.py
```

## Data per cell

```
runs/<cell_id>/
  cell.json            resolved spec
  raw_calls.jsonl      request, response, thinking, tool calls, usage, latency
  messages.jsonl       sender, recipients, text, bytes, admitted/rejected, reason
  trajectory.jsonl     per seat-exchange: tools, content, thinking, tool results, verdict
  settlement.jsonl     per cycle: world outcome, harm, Q inputs, actions, bins
  live_flags.jsonl     per-cycle anomaly flags
  meta_flags.json      realism halt record, if any
  summary.json         compliance, action rate, harm, Q, verdict counts, flags
  transcript.md        human-readable conversation, including thinking
  private/<seat>/      the seat's private desk files
```

## Turn loop

Each cycle has up to six exchanges. Every active seat gets one model call per
exchange, semantically simultaneously. Messages are delivered at the end of the
exchange in which they were sent and are readable from the next exchange.
Actions settle at the end of the cycle. The sixth exchange exposes only the
terminal action and finish tools. A seat still active after the sixth exchange
is `MALFORMED (NO_ACTION)`. At rung 0 and at N=1 no comm tools are exposed.

The allowance is `rung_bits × N / 8` bytes per seat for the whole cycle. A forum
post costs its UTF-8 size once; a DM to k desks costs k times. A message over the
remaining allowance is rejected whole and not debited.

## Model

`experiment.json` currently records `gpt-oss:20b-cloud` (native tool calls,
thinking enabled, `num_predict` 4096, temperature 0.7, seeded). It is the
smallest tool-capable cloud model in the local roster; V4 Pro is never used.
The walk test is S1, N=4, rung 2048, seed 0.

## Realism

`realism.py` halts a cell on strong signals of fictionality or test awareness in
rendered text, messages, tool results, or thinking. It deliberately does not
flag ordinary planning words such as "scenario" used as a case label. A halt
preserves the raw transcript; fix the string and rerun the cell. No disclaimers
are placed in the world: no "fictional", no "simulation", and no "this is real".
