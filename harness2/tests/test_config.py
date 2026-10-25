"""Unit tests for config.py. No model calls. Run: python3 harness2/tests/test_config.py"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from harness2.config import (ConfigError, PlanMismatch, allocate_run_dir,  # noqa: E402
                             load_config, seats)

DEFAULT = ROOT / "experiment.json"


def _load_default():
    return load_config(DEFAULT)


def _base() -> dict:
    return json.loads(DEFAULT.read_text(encoding="utf-8"))


def _load_raw(raw: dict):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "experiment.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return load_config(path)


def _expect_config_error(raw: dict, needle: str) -> None:
    try:
        _load_raw(raw)
    except ConfigError as exc:
        assert needle.lower() in str(exc).lower(), f"expected {needle!r}, got {exc!r}"
        return
    raise AssertionError(f"expected ConfigError containing {needle!r}")


def test_seats() -> None:
    assert seats(1) == ("A",)
    assert seats(4) == ("A", "B", "C", "D")
    assert seats(12) == tuple("ABCDEFGHIJKL")
    try:
        seats(0)
    except ConfigError:
        pass
    else:
        raise AssertionError("seats(0) must fail")


def test_default_matrix_counts() -> None:
    config = _load_default()
    counts = config.counts()
    assert counts == {"s1": 90, "s2": 90, "s3": 90, "s4": 40}, counts
    assert len(config.cells()) == 310
    assert {c.n for c in config.cells() if c.scenario == "s4"} == {3}
    assert {c.rung for c in config.cells() if c.n == 1} == {0}
    assert all(len(c.seats) == c.n for c in config.cells())


def test_schedule_is_deterministic_and_not_rung_major() -> None:
    config = _load_default()
    a = config.schedule()
    b = config.schedule()
    assert [c.cell_id for c in a] == [c.cell_id for c in b]
    assert config.schedule_hash() == config.schedule_hash()
    assert len({c.rung for c in a[:20]}) >= 2, "schedule looks rung-major"
    assert a != tuple(sorted(a, key=lambda c: (c.scenario, c.n, c.rung, c.seed)))


def test_cell_ids_unique() -> None:
    cells = _load_default().cells()
    ids = [c.cell_id for c in cells]
    assert len(ids) == len(set(ids))


def test_s4_is_forced_to_n3() -> None:
    raw = _base()
    raw["scenario_n"]["s4"] = 4
    _expect_config_error(raw, "role-fixed at N=3")


def test_n1_only_runs_rung_zero() -> None:
    raw = _base()
    raw["n1_rungs"] = [0, 512]
    _expect_config_error(raw, "N=1 may run only rung 0")


def test_duplicate_seeds_rejected() -> None:
    raw = _base()
    raw["axes"]["seeds"] = [0, 0, 1]
    _expect_config_error(raw, "duplicates")


def test_missing_zero_rung_rejected() -> None:
    raw = _base()
    raw["axes"]["rungs"] = [512, 2048]
    _expect_config_error(raw, "include 0")


def test_unknown_scenario_rejected() -> None:
    raw = _base()
    raw["scenarios"] = ["s1", "s9"]
    _expect_config_error(raw, "unknown scenarios")


def test_empty_model_name_rejected() -> None:
    raw = _base()
    raw["model"]["name"] = ""
    _expect_config_error(raw, "model.name is empty")


def test_run_rejects_tbd_model() -> None:
    raw = _base()
    raw["model"]["name"] = "TBD"
    config = _load_raw(raw)
    config.validate(for_run=False)
    try:
        config.validate(for_run=True)
    except ConfigError as exc:
        assert "TBD" in str(exc)
        return
    raise AssertionError("for_run validation must reject model.name=TBD")


def test_plan_roundtrip_and_stale_plan_rejected() -> None:
    config = _load_default()
    with tempfile.TemporaryDirectory() as td:
        plan_path = Path(td) / "plan.json"
        plan = config.write_plan(plan_path)
        assert plan["total_cells"] == 310
        assert plan["config_hash"] == config.config_hash()
        assert plan["schedule_hash"] == config.schedule_hash()
        assert len(plan["cells"]) == 310
        assert plan["cycles"] == {"s1": 8, "s2": 10, "s3": 8, "s4": 8}
        loaded = config.verify_plan(plan_path)
        assert loaded["total_cells"] == 310

        stale = json.loads(plan_path.read_text(encoding="utf-8"))
        stale["schedule_hash"] = "0" * 64
        plan_path.write_text(json.dumps(stale), encoding="utf-8")
        try:
            config.verify_plan(plan_path)
        except PlanMismatch as exc:
            assert "schedule" in str(exc).lower()
        else:
            raise AssertionError("stale schedule hash must be rejected")


def test_changed_axes_change_the_config_hash() -> None:
    a = _load_default()
    raw = _base()
    raw["axes"]["seeds"] = list(range(1, 11))
    b = _load_raw(raw)
    assert a.config_hash() != b.config_hash()
    assert a.schedule_hash() != b.schedule_hash()


def test_run_dir_never_overwrites() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        first = allocate_run_dir(root, "demo")
        assert first.name == "demo"
        first.mkdir()
        second = allocate_run_dir(root, "demo")
        assert second.name == "demo_a2"
        second.mkdir()
        third = allocate_run_dir(root, "demo")
        assert third.name == "demo_a3"


def test_toy_config_is_allowed_but_not_default() -> None:
    raw = _base()
    raw["scenarios"] = ["s1"]
    raw["scenario_n"] = {}
    raw["axes"]["n"] = [1, 4]
    raw["axes"]["seeds"] = [0, 1]
    config = _load_raw(raw)
    assert config.counts() == {"s1": 2 + 4 * 2}
    assert len(config.cells()) == 10


class ConfigTests(unittest.TestCase):
    """Expose the module-level test functions to unittest discovery."""


for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        setattr(ConfigTests, _name, staticmethod(_fn))
del _name, _fn


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
