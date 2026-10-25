"""comms/observation.py — the one shared public signal, coarsened and jittered.

Every seat in a cycle sees the same published number.  It is snapped to a
declared grid and then given fresh seeded jitter, so a seat cannot invert it to
recover another desk's exact posted price.  The jitter is regenerated per cell
and per cycle, and is identical across arms.
"""

from __future__ import annotations

import math
import random


class ScalarChannel:
    def __init__(self, step: float, seed: int) -> None:
        if step <= 0:
            raise ValueError("step must be > 0")
        self.step = float(step)
        self._rng = random.Random(f"scalar:{seed}")

    def coarsen(self, value: float) -> float:
        return round(float(value) / self.step) * self.step

    def publish(self, value: float) -> float:
        return round(self.coarsen(value) + self._rng.uniform(-self.step / 2,
                                                             self.step / 2), 2)

    def capacity_bits(self, value_range: float) -> float:
        levels = max(1.0, float(value_range) / self.step)
        return math.log2(levels)
