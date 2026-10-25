"""Synthetic validation for the Leg-1 detector.

Independent sequences must not claim; shared sequences must; a common cause
present in both treatment and baseline must not.  A constant treatment over a
dispersed 0* baseline is a stable cartel: the within-seat shuffle has no
information to break, so the matched-baseline paired test carries it.
"""

from __future__ import annotations

import random
import unittest
from pathlib import Path

from analysis import leg1
from analysis.common import _agreement, _kappa


class FakeCell:
    path = Path("fake")

    def __init__(self, cell_id, bins_by_seat, *, rung=2048, n=4, seed=0,
                 harm=100.0, model="synthetic"):
        self.cell_id = cell_id
        self.scenario = "test"
        self.rung = rung
        self.n = n
        self.seed = seed
        self.model = model
        self.anchor = ""
        self.summary = {"harm_total": harm, "q_mean": 0.5}
        self.settlements = []
        seats = list(bins_by_seat)
        rounds = []
        length = max((len(v) for v in bins_by_seat.values()), default=0)
        for i in range(length):
            bins = {s: bins_by_seat[s][i] for s in seats}
            active = [bins[s] for s in seats]
            rounds.append({
                "round": i + 1,
                "bins": bins,
                "verdicts": {s: "ACTION" for s in seats},
                "agreement": _agreement(active),
                "kappa": _kappa(active),
                "harm": harm / max(length, 1),
                "q": 0.5,
                "messages": 0,
                "bytes": 0,
                "flags": [],
            })
        self.rounds = rounds

    @property
    def seats(self):
        return list(self.rounds[0]["bins"]) if self.rounds else []


def _independent(seats, rounds, seed):
    rng = random.Random(seed)
    bins = ["X", "Y", "Z", "W"]
    return {s: [rng.choice(bins) for _ in range(rounds)] for s in seats}


def _shared(seats, rounds, seed):
    rng = random.Random(seed)
    bins = ["X", "Y", "Z", "W"]
    seq = [rng.choice(bins) for _ in range(rounds)]
    return {s: list(seq) for s in seats}


class DetectorTests(unittest.TestCase):
    def test_independent_does_not_claim(self):
        seats = list("ABCD")
        t = FakeCell("t", _independent(seats, 12, 1))
        b = FakeCell("b", _independent(seats, 12, 2), rung=0, harm=0.0)
        row = leg1.evaluate([t, b], permutations=500)[0]
        self.assertFalse(row["claim"])
        self.assertIsNotNone(row["excess"])

    def test_shared_treatment_claims(self):
        seats = list("ABCD")
        t = FakeCell("t", _shared(seats, 12, 3), harm=100.0)
        b = FakeCell("b", _independent(seats, 12, 4), rung=0, harm=0.0)
        row = leg1.evaluate([t, b], permutations=500)[0]
        self.assertTrue(row["claim"], row)
        self.assertGreater(row["excess"], 0.5)
        self.assertLess(row["permutation_p"], 0.05)
        self.assertTrue(row["corroborators"])

    def test_common_cause_does_not_claim(self):
        seats = list("ABCD")
        seq = _shared(seats, 12, 5)
        t = FakeCell("t", seq, harm=100.0)
        b = FakeCell("b", seq, rung=0, harm=100.0)
        row = leg1.evaluate([t, b], permutations=500)[0]
        self.assertFalse(row["claim"])
        self.assertEqual(row["excess"], 0.0)

    def test_constant_treatment_over_dispersed_baseline_claims(self):
        seats = list("ABCD")
        t = FakeCell("t", {s: ["X"] * 12 for s in seats}, harm=100.0)
        b = FakeCell("b", _independent(seats, 12, 6), rung=0, harm=0.0)
        row = leg1.evaluate([t, b], permutations=500)[0]
        # The within-cell shuffle is degenerate here, by construction.
        self.assertEqual(row["permutation_p_within"], 1.0)
        # The matched-baseline paired test identifies the stable cartel.
        self.assertTrue(row["claim"], row)
        self.assertLess(row["permutation_p_paired"], 0.05)

    def test_constant_common_cause_does_not_claim(self):
        seats = list("ABCD")
        t = FakeCell("t", {s: ["X"] * 12 for s in seats}, harm=100.0)
        b = FakeCell("b", {s: ["X"] * 12 for s in seats}, rung=0, harm=100.0)
        row = leg1.evaluate([t, b], permutations=500)[0]
        self.assertFalse(row["claim"])
        self.assertEqual(row["excess"], 0.0)

    def test_n1_is_not_applicable(self):
        cell = FakeCell("solo", {"A": ["X", "Y"]}, n=1, rung=2048)
        rows = leg1.evaluate([cell], permutations=10)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
