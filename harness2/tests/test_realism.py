"""Realism at build time, not at run time.

The engine no longer pre-scans every rendered prompt before a batch.  Instead
this test renders each scenario's three-part brief and its tool surface once
and fails on meta vocabulary.  A prompt regression is caught here, before any
cell is run, without a runtime check in the hot path.
"""

from __future__ import annotations

import unittest

from harness2.comms.channel import Message
from harness2.realism import MetaFlagError, scan
from harness2.scenario import load_scenario


class TestScenarioPrompts(unittest.TestCase):
    SCENARIOS = ("s1", "s2", "s3", "s4")

    def test_briefs_and_tools_are_in_world(self):
        for name in self.SCENARIOS:
            sc = load_scenario(name)
            seats = [chr(ord("A") + i) for i in range(sc.default_seats)]
            world = sc.create_world(seats, 0)
            scan(sc.world_brief(world), where=f"{name} world brief")
            for seat in seats:
                scan(sc.seat_brief(world, seat), where=f"{name} seat brief {seat}")
                for tool in sc.action_tools(world, seat):
                    scan(f"{tool.name} {tool.description}",
                         where=f"{name} tool {tool.name}")

    def test_the_communicating_brief_is_in_world_too(self):
        # The rung>0 paragraph is a different branch of every brief, and it is
        # the one live cells actually use.  The engine sets world["channel"]
        # after construction, so a world built by create_world alone never
        # exercises it.
        for name in self.SCENARIOS:
            sc = load_scenario(name)
            seats = [chr(ord("A") + i) for i in range(sc.default_seats)]
            world = sc.create_world(seats, 0)
            world["channel"] = True
            world["rung"] = 2048
            world["peers"] = list(seats)
            scan(sc.world_brief(world), where=f"{name} communicating brief")

    def test_each_cycles_opening_is_in_world(self):
        for name in self.SCENARIOS:
            sc = load_scenario(name)
            seats = [chr(ord("A") + i) for i in range(sc.default_seats)]
            world = sc.create_world(seats, 0)
            world["channel"] = True
            world["rung"] = 2048
            world["peers"] = list(seats)
            sc.warmup(world, seats)
            sc.new_round(world, 0)
            for seat in seats:
                obs = sc.observation(world, seat, 0)
                text = sc.opening(world, seat, obs, 1, 6, 768)
                scan(text, where=f"{name} opening {seat}")

    def test_world_brief_is_the_same_for_every_seat(self):
        for name in self.SCENARIOS:
            sc = load_scenario(name)
            seats = [chr(ord("A") + i) for i in range(sc.default_seats)]
            world = sc.create_world(seats, 0)
            briefs = {sc.world_brief(world) for _ in seats}
            self.assertEqual(len(briefs), 1, f"{name}: world brief varies by seat")

    def test_one_seat_brief_cannot_leak_into_another(self):
        for name in self.SCENARIOS:
            sc = load_scenario(name)
            seats = [chr(ord("A") + i) for i in range(sc.default_seats)]
            if len(seats) < 2:
                continue
            world = sc.create_world(seats, 0)
            first = sc.seat_brief(world, seats[0])
            for other in seats[1:]:
                self.assertNotEqual(first, sc.seat_brief(world, other),
                                    f"{name}: two seats share one brief")


class TestMessageRendering(unittest.TestCase):
    def test_common_room_and_direct_notes_read_differently(self):
        sc = load_scenario("s1")
        seats = ["A", "B"]
        world = sc.create_world(seats, 0)
        room = Message(0, 1, "A", ("B",), "hold at 1,200", channel="common_room")
        note = Message(0, 1, "A", ("B",), "only us", channel="direct")
        self.assertIn("common room", sc.message_line(world, room))
        line = sc.message_line(world, note)
        self.assertIn("direct note", line)
        self.assertIn("B", line)


if __name__ == "__main__":
    unittest.main()
