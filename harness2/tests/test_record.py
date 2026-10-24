"""test_record.py – tests for record.py (R2)."""

import os
import json
import tempfile
import pathlib

from harness2.record import RunRecorder


def test_record_rounds_and_summary(tmp_path):
    cell_spec = {"scenario": "demo", "rung_bits": 8, "topology": "common", "n": 2, "family": "test", "seed": 123}
    gates = {"wg": 1}
    recorder = RunRecorder(str(tmp_path), cell_spec, gates)

    # round 1 for seat A
    recorder.log_round(round=1, seat="A", observation={}, action={"play": 1}, verdict="legal", latency_s=0.1)
    recorder.log_message("A", "hello", 16, "admit", ["B"])
    # seat B round 1
    recorder.log_round(round=1, seat="B", observation={}, action={"play": 2}, verdict="legal", latency_s=0.2)
    recorder.log_message("B", "hi", 8, "admit", ["A"])
    # malformed seat A round 2
    recorder.log_round(round=2, seat="A", observation={}, action={"play": 3}, verdict="malformed", latency_s=0.3)
    recorder.log_message("A", "oops", 10, "infra", ["B"])

    recorder.finalise({"trial": 1})

    # trajectory
    traj = list(tmp_path.glob("trajectory.jsonl"))
    assert len(traj)==1
    lines = traj[0].read_text().splitlines()
    assert len(lines)==3

    # summary
    summary_file = tmp_path / 'summary.json'
    assert summary_file.exists()
    summary = json.loads(summary_file.read_text())
    # compliance: 2 legal out of 3 seat-rounds
    assert abs(summary['compliance_rate']-2/3)<1e-6
    assert summary['verdict_code']=="INFRA"

    # transcript contains marker
    trans = (tmp_path / 'transcript.md').read_text()
    assert "hello" in trans

    print("test passed")

if __name__=="__main__":
    test_record_rounds_and_summary()
