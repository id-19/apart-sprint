"""sweep.py — sequential multi-model S1 run with stop-on-breakage.

Runs the same 10-cell design (S1, N=4, rungs {0, 2048}, seeds 0-4) for each
config in MODEL_SWEEP, one model at a time, resuming finished cells.  Between
models it inspects the summaries that model wrote and refuses to continue the
sweep if anything looks broken:

  - any halted summary (realism gate or infra)
  - a non-zero exit from the runner
  - no completed cell for the model after the run
  - transport-error rate above 20% on the model's newest attempts

Every decision is appended to analysis_out/sweep.log; the human log stays
EXPERIMENT_LOG.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

MODEL_SWEEP = [
    "pilot_gemma4_s1.json",
    "pilot_glm_s1.json",
    "pilot_deepseek_s1.json",
    "pilot_nemotron_s1.json",
]

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "analysis_out" / "sweep.log"

# A summary is only evidence for the design that produced it.  Both versions
# ship in every summary; resume and the health check compare them, so a cell
# written under an older harm measure can neither be skipped as finished nor
# counted in a model's total.
from harness2.engine import ENGINE_VERSION  # noqa: E402
from harness2.scenario import load_scenario  # noqa: E402


def _log(text: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _model(config: str) -> str:
    return json.loads((ROOT / config).read_text())["model"]["name"]


def _alive(config: str) -> bool:
    out = subprocess.run(["ps", "-axo", "command"], capture_output=True,
                         text=True).stdout
    return any(("harness2.entry run" in line) and (config in line)
               for line in out.splitlines())


def _summaries(model: str) -> list[dict]:
    rows = []
    for p in Path(ROOT / "runs").glob("s1_*/summary.json"):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if s.get("model") == model:
            rows.append(s)
    return rows


def _transport_errors(model: str) -> tuple[int, int]:
    calls = errors = 0
    for p in Path(ROOT / "runs").glob("s1_*/raw_calls.jsonl"):
        for line in p.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("model") != model:
                continue
            calls += 1
            if r.get("status") != "ok":
                errors += 1
    return errors, calls


def _current_done(model: str) -> tuple[dict[str, dict], int, int]:
    """Completed cells under the current design, plus stale/halted counts."""
    rows = _summaries(model)
    done: dict[str, dict] = {}
    halted = stale = 0
    for s in rows:
        if s.get("halted"):
            halted += 1
            continue
        try:
            version = load_scenario(s.get("scenario", "s1")).version
        except (KeyError, ImportError):
            stale += 1
            continue
        if summary_stale(s, version):
            stale += 1
            continue
        if s.get("cycles_run", 0) >= 8:
            prev = done.get(s["cell_id"])
            if prev is None or s.get("finished_at", 0) >= prev.get("finished_at", 0):
                done[s["cell_id"]] = s
    return done, halted, stale


def summary_stale(summary: dict, scenario_version: str) -> bool:
    return (summary.get("scenario_version") != scenario_version
            or summary.get("engine_version") != ENGINE_VERSION)


def _verdict(model: str) -> str | None:
    """None = healthy, else the reason the sweep must stop.

    Infra halts are not a stop: a dropped connection or a sleeping machine
    writes a halted summary, and resume reruns that cell.  Realism halts never
    write a summary at all — they abort the batch with exit code 2, which the
    caller turns into a stop.  Only a *pattern* of transport failure, a
    compliance collapse, or an empty batch stops the sweep.
    """
    done, halted, stale = _current_done(model)
    if halted:
        _log(f"{model}: {halted} infra-halted attempt(s) — resume will rerun them")
    if stale:
        _log(f"{model}: {stale} stale cell(s) from an earlier design — "
             f"they are rerun, not counted")
    if not done:
        return "no completed cell"
    bad = [cid for cid, s in done.items() if s.get("compliance", 1.0) < 0.5]
    if bad:
        return f"compliance below 0.50 in {bad}"
    errors, calls = _transport_errors(model)
    if calls >= 30 and errors / calls > 0.20:
        return f"transport errors {errors}/{calls}"
    return None


def main() -> int:
    _log("sweep start: " + ", ".join(MODEL_SWEEP))
    for config in MODEL_SWEEP:
        model = _model(config)
        while _alive(config):
            _log(f"{model}: waiting for the live runner on {config}")
            time.sleep(30)
        reason = _verdict(model)
        if reason:
            _log(f"{model}: STOP — {reason}")
            return 1
        if _summaries(model):
            _log(f"{model}: resuming {config} (finished cells skipped)")
        plan = ROOT / "runs" / f"plan-{Path(config).stem}.json"
        rc = subprocess.run([sys.executable, "-m", "harness2.entry", "plan",
                             "--config", config, "--out", str(plan)],
                            cwd=ROOT, capture_output=True, text=True)
        if rc.returncode != 0:
            _log(f"{model}: STOP — plan failed: {rc.stderr.strip()[:200]}")
            return 1
        _log(f"{model}: running {config}")
        run = subprocess.run([sys.executable, "-m", "harness2.entry", "run",
                              "--config", config, "--approve", str(plan),
                              "--all"],
                             cwd=ROOT, capture_output=True, text=True)
        tail = " | ".join((run.stdout or "").strip().splitlines()[-3:])
        _log(f"{model}: runner exit {run.returncode} — {tail[:400]}")
        reason = _verdict(model) if run.returncode == 0 else \
            f"runner exit {run.returncode}: {(run.stderr or '').strip()[:200]}"
        if reason:
            _log(f"{model}: STOP — {reason}")
            return 1
        rows, _, _ = _current_done(model)
        harm = sum(s.get("harm_total", 0.0) for s in rows.values())
        msgs = sum(s.get("messages_admitted", 0) for s in rows.values())
        _log(f"{model}: OK — {len(rows)} current cells, harm {harm:,.0f}, "
             f"msgs {msgs}")
    _log("sweep complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
