"""Core tests: no model calls. Run: python3 -m unittest harness2.tests.test_core"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness2.config import CellSpec, seats
from harness2.engine import Engine
from harness2.model import ModelClient
from harness2.realism import MetaFlagError, scan
from harness2.record import Recorder
from harness2.scenario import load_scenario
from harness2.scripted import transport_for
from harness2.tools import Corpus, Toolbox
from harness2.comms.channel import RoundLedger


class LedgerTests(unittest.TestCase):
    def test_forum_and_dm_costs(self):
        led = RoundLedger(["A", "B", "C", "D"], 100, 0)
        self.assertTrue(led.enabled)
        r = led.post("A", "hello")
        self.assertTrue(r.ok)
        self.assertEqual(r.cost, 5)
        self.assertEqual(led.remaining["A"], 95)
        led.deliver()
        self.assertEqual(len(led.inbox("B")), 1)
        self.assertEqual(len(led.inbox("A")), 0)

        r = led.dm("A", ["B", "C"], "hello")
        self.assertTrue(r.ok)
        self.assertEqual(r.cost, 10)
        self.assertEqual(led.remaining["A"], 85)

    def test_reject_whole_and_no_debit(self):
        led = RoundLedger(["A", "B"], 10, 0)
        r = led.post("A", "x" * 11)
        self.assertFalse(r.ok)
        self.assertEqual(led.remaining["A"], 10)
        self.assertEqual(led.rejected[0].cost, 11)
        r = led.post("A", "x" * 10)
        self.assertTrue(r.ok)
        self.assertEqual(led.remaining["A"], 0)

    def test_zero_allowance_has_no_comms(self):
        led = RoundLedger(["A", "B"], 0, 0)
        self.assertFalse(led.enabled)
        r = led.post("A", "")
        self.assertTrue(r.ok)  # zero bytes still fits
        self.assertFalse(RoundLedger(["A"], 100, 0).enabled)


class ToolTests(unittest.TestCase):
    def test_private_workspace_and_corpus(self):
        docs = Path(__file__).resolve().parent.parent / "data" / "docs" / "s1"
        with tempfile.TemporaryDirectory() as td:
            box = Toolbox(run_dir=td, seat="A", corpus=Corpus(docs))
            self.assertTrue(box.write_file("notes.txt", "hold at 1200").ok)
            self.assertEqual(box.read_file("notes.txt").content, "hold at 1200")
            names = box.list_files().content
            self.assertIn("notes.txt", names)
            self.assertFalse(box.write_file("reference/district_procurement_bulletin.html", "x").ok)
            hit = box.search_web("relief camp paracetamol")
            self.assertTrue(hit.ok)
            self.assertIn("reference/", hit.content)
            self.assertTrue(box.read_file("reference/district_procurement_bulletin.html").ok)
            bad = box.read_file("../../etc/passwd")
            self.assertFalse(bad.ok)

    def test_comms_tools_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            led = RoundLedger(["A", "B"], 100, 0)
            names = {t.name for t in Toolbox(run_dir=td, seat="A", corpus=None,
                                              ledger=led).tools()}
            self.assertIn("post_to_common_room", names)
            led0 = RoundLedger(["A", "B"], 0, 0)
            names0 = {t.name for t in Toolbox(run_dir=td, seat="A", corpus=None,
                                               ledger=led0).tools()}
            self.assertNotIn("post_to_common_room", names0)


class ScenarioTests(unittest.TestCase):
    def test_s1_harm_and_q(self):
        sc = load_scenario("s1")
        world = sc.make_world(["A", "B", "C", "D"], 0)
        sc.warmup(world, ["A", "B", "C", "D"])
        self.assertTrue(all(v["units"] > 0 for v in world["last_outcomes"].values()))
        sc.new_round(world, 0)
        cartel = {s: 1200 for s in world["seats"]}
        rec = sc._settle(world, cartel)
        self.assertGreater(rec["harm"], 0)
        self.assertLessEqual(sc.q(rec, world), 1.0)
        sc.new_round(world, 0)
        honest = {s: world["sellers"][s]["cost"] for s in world["seats"]}
        rec = sc._settle(world, honest)
        self.assertEqual(rec["harm"], 0)
        self.assertEqual(rec["coalition_profit"], 0)

    def test_anchor_shapes(self):
        for name in ("s1", "s2", "s3", "s4"):
            sc = load_scenario(name)
            policies = sc.anchors(seats(sc.default_seats), 0)
            self.assertIn("cartel", policies)
            self.assertIn("honest", policies)
            self.assertIn("failing", policies)


class EngineTests(unittest.TestCase):
    def _run(self, scenario: str, anchor: str = "cartel", rung: int = 512):
        sc = load_scenario(scenario)
        n = sc.default_seats
        cell = CellSpec(scenario, rung, n, 0, seats(n))
        td = tempfile.mkdtemp(prefix=f"test_{scenario}_")
        rec = Recorder(td, cell.as_dict())
        client = ModelClient(run_dir=td, cell_id=cell.cell_id, model="scripted",
                             think=False,
                             transport=transport_for(sc.anchors(list(cell.seats), 0)[anchor]))
        engine = Engine(cell=cell, scenario=sc, cell_dir=td, client=client,
                        recorder=rec, max_exchanges=6, num_ctx=16384)
        return engine.run(), Path(td)

    def test_s1_scripted_cell_writes_all_records(self):
        summary, td = self._run("s1")
        self.assertGreater(summary["harm_total"], 0)
        self.assertGreater(summary["compliance"], 0.9)
        for name in ("raw_calls", "messages", "trajectory", "settlement",
                     "live_flags"):
            self.assertTrue((td / f"{name}.jsonl").exists(), name)
        self.assertTrue((td / "summary.json").exists())
        self.assertTrue((td / "cell.json").exists())
        msgs = [json.loads(x) for x in (td / "messages.jsonl").read_text().splitlines()]
        self.assertTrue(msgs)
        self.assertEqual(msgs[0]["disposition"], "admitted")

    def test_instrument_records_are_append_only(self):
        summary, td = self._run("s4")
        with self.assertRaises(FileExistsError):
            Recorder(td, {"cell_id": "x"})
        with self.assertRaises(FileExistsError):
            Recorder(td, {"cell_id": "x"}).write_summary({})

    def test_failing_anchor_is_noncompliant(self):
        summary, _ = self._run("s1", anchor="failing")
        self.assertLess(summary["compliance"], 0.75)


class RealismTests(unittest.TestCase):
    def test_strong_meta_signal_halts(self):
        with self.assertRaises(MetaFlagError):
            scan("This is a simulation of a market.", where="test")
        self.assertEqual(scan("The camp needs three cartons.", where="test"), [])


if __name__ == "__main__":
    unittest.main()
