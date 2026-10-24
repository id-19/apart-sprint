"""Test agents.py mesh addressing + turn classification. Run: python3 harness2/tests/test_agents.py"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import run_turn  # noqa: E402
from comms.channel import Channel  # noqa: E402
from comms.observation import observation  # noqa: E402
from ollama_client import OllamaClient  # noqa: E402


def _client(tmp, transport):
    return OllamaClient(run_dir=tmp, cell="c", model="m", seed=0, transport=transport)


def test_mesh_addressed_message_goes_to_addressee_only() -> None:
    ch = Channel("mesh", ["A", "B", "C"], 1024)
    c = _client(tempfile.mkdtemp(), lambda p: {"message": {"content":
                                           "@B MSG: hold at 13\nPRICE: 13"}})
    turn = run_turn(c, ch, "A", 0, observation(0, 0, "x"), [], 1024)
    assert turn.verdict == "LEGAL" and turn.price == 13.0
    assert turn.messages_admitted == 1
    ch.advance_round()
    assert len(ch.inbox("B")) == 1 and ch.inbox("C") == []


def test_mesh_unaddressed_broadcasts_to_all_others() -> None:
    ch = Channel("mesh", ["A", "B", "C"], 1024)
    c = _client(tempfile.mkdtemp(), lambda p: {"message": {"content":
                                           "MSG: hold\nPRICE: 13"}})
    turn = run_turn(c, ch, "A", 0, observation(0, 0, "x"), [], 1024)
    assert turn.messages_admitted == 1
    ch.advance_round()
    assert len(ch.inbox("B")) == 1 and len(ch.inbox("C")) == 1


def test_no_price_is_malformed() -> None:
    ch = Channel("common", ["A", "B"], 1024)
    c = _client(tempfile.mkdtemp(), lambda p: {"message": {"content":
                                               "I am undecided."}})
    turn = run_turn(c, ch, "A", 0, observation(0, 0, "x"), [], 1024)
    assert turn.verdict == "MALFORMED" and turn.price is None


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
