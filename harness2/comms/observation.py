"""comms/observation.py — the per-seat §1.0 observation (R2, C2).

Each seat sees exactly three things per round: its own action, one coarsened+jittered
common scalar, and its own outcome. The common scalar is the ONLY non-message signal
shared by all seats, so it is the implicit channel. Coarsen it to a declared grid and add
fresh unmodellable jitter each round so an agent cannot invert it to recover others'
exact actions. Identical coarsening/jitter across arms; capacity identical across arms.
"""

from __future__ import annotations

import hashlib
import random


class ScalarChannel:
    """Coarsened + jittered common scalar for one scenario.

    step       : grid spacing of the public scalar (coarsening)
    jitter_rng : fresh uniform perturbation in [-step/2, step/2) each publish
    """

    def __init__(self, step: float, seed: int) -> None:
        if step <= 0:
            raise ValueError("step must be > 0")
        self.step = float(step)
        self._rng = random.Random(seed)

    def coarsen(self, value: float) -> float:
        """Snap to the grid centre of its cell."""
        return round(value / self.step) * self.step

    def publish(self, value: float) -> float:
        """Coarsen then add fresh jitter. What every seat sees."""
        return self.coarsen(value) + self._rng.uniform(-self.step / 2, self.step / 2)

    def capacity_bits(self, value_range: float) -> float:
        """Upper bound on what the bus can carry: log2(range/step) bits per publish.
        A coarse scalar is a hard cap on the implicit channel (C2)."""
        import math
        levels = max(1.0, value_range / self.step)
        return math.log2(levels)


class DeterministicJitter(ScalarChannel):
    """Same interface, but the jitter is a pure function of (round, value) so it is
    reproducible from the log without storing RNG state. Used by default."""

    def __init__(self, step: float, seed: int) -> None:
        super().__init__(step, seed)
        self._seed = seed

    def publish(self, value: float) -> float:
        key = f"{self._seed}|{value!r}".encode()
        u = (int.from_bytes(hashlib.sha256(key).digest()[:8], "big") / 2**64) - 0.5
        return self.coarsen(value) + u * self.step


def observation(own_action, common_scalar, own_outcome) -> dict:
    """The exactly-three-key §1.0 observation. Anything more is a leak."""
    return {
        "own_action": own_action,
        "common_scalar": common_scalar,
        "own_outcome": own_outcome,
    }
