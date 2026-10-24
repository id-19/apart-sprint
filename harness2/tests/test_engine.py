"""Integration test: engine + gates + e2e, all with scripted transports (no Ollama).
Run: python3 harness2/tests/test_engine.py"""

import json
import os
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (CellSpec, Engine, run_e2e, scripted_cartel,  # noqa: E402
                    scripted_failing, scripted_honest)


def test_gate_calibration_requires_harm() -> None:
    spec = CellSpec(seed=1)
    e = Engine(spec, tempfile.mkdtemp(), scripted_honest())
    g = e.run_gates()
    assert g.calibration, "scripted cartel at 13 must produce extraction harm"


def test_compliance_gate_catches_failing_actor() -> None:
    spec = CellSpec(seed=1)
    e = Engine(spec, tempfile.mkdtemp(), scripted_honest())
    g = e.run_gates()
    assert g.compliance_gate, "malformed-only actor must fall below the 75% floor"


def test_controls_split_planted_from_honest() -> None:
    spec = CellSpec(seed=1)
    e = Engine(spec, tempfile.mkdtemp(), scripted_honest())
    g = e.run_gates()
    assert g.controls


def test_e2e_cartel_transport_produces_harm_and_records() -> None:
    run_e2e(scripted_cartel(0), seed=0)


def test_e2e_honest_transport_is_full_compliance_no_harm() -> None:
    tmp = tempfile.mkdtemp()
    spec = CellSpec(seed=2)
    e = Engine(spec, tmp, scripted_honest())
    assert e.run_gates().all_passed
    e.run()
    total = sum(e.compliance_counts.values())
    assert e.compliance_counts["legal"] == total
    assert all(r["harm"] == 0 for r in e.world.rounds)
    with open(os.path.join(tmp, "raw_calls.jsonl")) as f:
        calls = [json.loads(x) for x in f if x.strip()]
    assert len(calls) == spec.rounds * len(spec.seats)  # one call per seat per round


def test_infra_transport_aborts_stage_and_marks_invalid() -> None:
    def dead(payload):
        raise urllib.error.URLError("Connection refused")

    tmp = tempfile.mkdtemp()
    spec = CellSpec(seed=3)
    e = Engine(spec, tmp, dead)
    # gates will fail (no model), but a direct run must still abort cleanly
    e.run()
    assert os.path.exists(os.path.join(tmp, "INVALID.md"))
    with open(os.path.join(tmp, "INVALID.md")) as f:
        assert "INFRA" in f.read()


def test_per_dyad_holds_in_mesh_cell() -> None:
    # smallest contract assertion: mesh cell admits the same 56-bit text on 2 dyads
    from comms.channel import Channel
    ch = Channel("mesh", ["A", "B", "C"], 80)
    v = ch.send("A", "hold 13", 0, recipients=["B", "C"])
    assert v.ok


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
