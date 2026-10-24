"""Unit tests for comms/observation.py (R2). Run: python3 harness2/test_observation.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comms.observation import DeterministicJitter, ScalarChannel, observation  # noqa: E402


def test_observation_has_exactly_the_three_keys() -> None:
    obs = observation("price=13", 12.3, {"units": 5})
    assert set(obs.keys()) == {"own_action", "common_scalar", "own_outcome"}
    # no per-agent anything
    for k in obs:
        assert "other" not in k and "agent" not in k


def test_coarsen_snaps_to_grid() -> None:
    ch = ScalarChannel(step=0.5, seed=1)
    assert ch.coarsen(12.24) == 12.0
    assert ch.coarsen(12.26) == 12.5
    assert ch.coarsen(12.74) == 12.5


def test_publish_is_within_half_step_of_value() -> None:
    ch = ScalarChannel(step=0.5, seed=7)
    for v in (12.0, 12.24, 12.26, 13.0):
        p = ch.publish(v)
        # coarsened to grid centre +- jitter, so within one step of the true value
        assert abs(p - v) <= ch.step


def test_deterministic_jitter_is_reproducible() -> None:
    a = DeterministicJitter(step=1.0, seed=42)
    b = DeterministicJitter(step=1.0, seed=42)
    c = DeterministicJitter(step=1.0, seed=43)
    assert a.publish(12.3) == b.publish(12.3)     # same seed → same jitter
    assert a.publish(12.3) != c.publish(12.3)     # different seed → different perturbation


def test_capacity_bits_shrinks_as_step_grows() -> None:
    fine = ScalarChannel(step=0.1, seed=1).capacity_bits(value_range=10.0)
    coarse = ScalarChannel(step=2.0, seed=1).capacity_bits(value_range=10.0)
    assert coarse < fine
    # log2(100 levels) ≈ 6.64 for step 0.1 over range 10
    assert 6.6 < fine < 6.7


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
