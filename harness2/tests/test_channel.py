"""Unit tests for comms/channel.py (R3). Run: python3 harness2/test_channel.py"""

import os
import sys

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, D)

from comms.channel import Channel  # noqa: E402


SEATS = ["A", "B", "C"]
CAP = 80          # 10 ASCII chars
OVER = "y" * 11   # 88 bits
OK = "hold 13"    # 56 bits


def test_common_post_reaches_all_others_next_round() -> None:
    ch = Channel("common", SEATS, CAP)
    v = ch.send("A", OK, round_sent=0)
    assert v.ok
    # nothing visible until the round advances
    assert ch.inbox("B") == []
    ch.advance_round()
    msgs = ch.inbox("B")
    assert len(msgs) == 1 and msgs[0].text == OK
    assert ch.inbox("A") == []          # sender never receives own post
    assert len(ch.inbox("C")) == 1


def test_common_post_over_cap_rejected_whole_logged() -> None:
    ch = Channel("common", SEATS, CAP)
    v = ch.send("A", OVER, round_sent=0)
    assert not v.ok and v.bits == 88
    assert len(ch.rejections) == 1
    r = ch.rejections[0]
    assert r.sender == "A" and r.text == OVER   # verbatim, even though dropped
    ch.advance_round()
    assert ch.inbox("B") == [] and ch.inbox("C") == []   # nothing was delivered


def test_mesh_cap_is_per_dyad_not_per_agent() -> None:
    # The design's settled unit: each dyad gets the rung cap. Same 56-bit text to
    # two dyads must be admitted on both (total 112 bits outgoing > rung 80) —
    # that is per-dyad budgeting; a per-agent budget would reject the second.
    ch = Channel("mesh", SEATS, CAP)
    v = ch.send("A", OK, round_sent=0, recipients=["B", "C"])
    assert v.ok
    ch.advance_round()
    assert len(ch.inbox("B")) == 1 and len(ch.inbox("C")) == 1


def test_mesh_over_cap_rejected_on_that_dyad_only() -> None:
    ch = Channel("mesh", SEATS, CAP)
    v = ch.send("A", OVER, round_sent=0, recipients=["B"])
    assert not v.ok
    # a separate in-cap message to C is unaffected
    v2 = ch.send("A", OK, round_sent=0, recipients=["C"])
    assert v2.ok
    ch.advance_round()
    assert ch.inbox("B") == []
    assert len(ch.inbox("C")) == 1


def test_mesh_requires_recipients_and_rejects_bad_ones() -> None:
    ch = Channel("mesh", SEATS, CAP)
    try:
        ch.send("A", OK, 0)          # no recipients
    except ValueError:
        pass
    else:
        raise AssertionError("mesh send without recipients must raise")
    ch.send("A", OK, 0, recipients=["A", "Z"])   # self + unknown
    assert len(ch.rejections) == 2               # both logged, nothing delivered
    ch.advance_round()
    assert ch.inbox("B") == []


def test_delivery_is_one_round_delayed() -> None:
    # two OTHER seats post; B watches messages arrive one round after each send.
    ch = Channel("common", SEATS, CAP)
    ch.send("A", "r0", 0)
    ch.advance_round()
    ch.send("C", "r1", 1)
    # C's r1 message is not yet visible to B
    assert [m.text for m in ch.inbox("B")] == ["r0"]
    ch.advance_round()
    assert [m.text for m in ch.inbox("B")] == ["r0", "r1"]
    # and a sender never receives its own post (bus excludes self)
    assert [m.text for m in ch.inbox("A")] == ["r1"]


def test_topology_and_seat_validation() -> None:
    for bad in (
        lambda: Channel("ring", SEATS, CAP),
        lambda: Channel("common", ["A", "A"], CAP),
    ):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid topology/duplicate seats must raise")


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
