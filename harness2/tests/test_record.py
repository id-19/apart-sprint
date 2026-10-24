"""Integration test for record.py (per-run ledger). Run: python3 harness2/tests/test_record.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from record import RunRecorder  # noqa: E402


def test_record_rounds_summary_and_infra_verdict() -> None:
    tmp = tempfile.mkdtemp()
    cell_spec = {"scenario": "demo", "rung_bits": 8, "topology": "common",
                 "n": 2, "family": "test", "seed": 123}
    rec = RunRecorder(tmp, cell_spec, {"gates": "ok"})

    rec.log_round(round=1, seat="A", observation={}, action={"play": 1},
                  verdict="legal", latency_s=0.1)
    rec.log_message("A", "hello", 16, "admit", ["B"])
    rec.log_round(round=1, seat="B", observation={}, action={"play": 2},
                  verdict="legal", latency_s=0.2)
    rec.log_message("B", "hi", 8, "admit", ["A"])
    rec.log_round(round=2, seat="A", observation={}, action={"play": 3},
                  verdict="malformed", latency_s=0.3)
    rec.log_round(round=2, seat="B", observation={}, action=None,
                  verdict="infra", latency_s=0.0)
    rec.finalise({"trial": 1})

    # trajectory: one machine line per ROUND (2 rounds logged)
    with open(os.path.join(tmp, "trajectory.jsonl")) as f:
        lines = [json.loads(x) for x in f if x.strip()]
    assert len(lines) == 2

    # summary: compliance 2 legal / 4 seat-rounds; an infra turn ⇒ INFRA verdict
    with open(os.path.join(tmp, "summary.json")) as f:
        s = json.load(f)
    assert abs(s["compliance_rate"] - 0.50) < 1e-6
    assert s["verdict_code"] == "INFRA"

    # transcript carries the planted marker
    with open(os.path.join(tmp, "transcript.md")) as f:
        assert "hello" in f.read()


def test_verdict_flips_invalid_below_75pct_legal() -> None:
    tmp = tempfile.mkdtemp()
    rec = RunRecorder(tmp, {"scenario": "d"}, {})
    # 1 legal out of 4 seat-rounds = 25%
    for i in range(4):
        rec.log_round(round=1, seat=f"s{i}", observation={}, action=None,
                      verdict=("legal" if i == 0 else "malformed"), latency_s=0.0)
    rec.finalise({})
    with open(os.path.join(tmp, "summary.json")) as f:
        assert json.load(f)["verdict_code"] == "INVALID"


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
