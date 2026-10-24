"""comms/channel.py — one Channel class; topology = common bus | mesh (R3).

Semantics (design §2.1, §2.2):
  * common: one post per round reaches all seats; the rung cap applies to each post.
  * mesh:   each directed dyad is its own channel; the rung cap applies PER DYAD, so an
            agent's total outgoing capacity scales as (N-1) × rung while each link stays
            at the rung. This is the confirmed design — do not "simplify" it.

Delivery is engine-driven: a message admitted in round t is visible to its recipients'
inbox at the start of round t+1 only. A seat never sees another seat's action, price, or
outcome here — only message text (§1.0).
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from typing import Dict, List, Optional

from budget import Verdict, check


@dataclass
class Message:
    round_sent: int
    sender: str
    recipients: tuple
    text: str

    @property
    def bits(self) -> int:
        from budget import count_bits
        return count_bits(self.text)


@dataclass
class Rejection:
    round_sent: int
    sender: str
    kind: str           # "over_cap" | "unknown_recipient" | "no_such_channel"
    detail: str
    bits: int
    text: str           # kept verbatim so a rejected message is still auditable


class Channel:
    """One scenario round's explicit channel. Seats are fixed strings."""

    def __init__(self, topology: str, seats: List[str], cap_bits_per_channel: Optional[int]) -> None:
        if topology not in ("common", "mesh"):
            raise ValueError(f"topology must be 'common' or 'mesh', got {topology!r}")
        if len(set(seats)) != len(seats):
            raise ValueError("seats must be unique")
        self.topology = topology
        self.seats = list(seats)
        self.cap = cap_bits_per_channel  # None = uncapped (internal/scripted use only)
        # admitted this round, delivered next round
        self._pending: List[Message] = []
        self._delivered: Dict[str, List[Message]] = {s: [] for s in seats}
        self.rejections: List[Rejection] = []
        self.admitted: List[Message] = []

    # ---- sending ----------------------------------------------------------
    def send(self, sender: str, text: str, round_sent: int,
             recipients: Optional[List[str]] = None) -> Verdict:
        """Attempt to send. Returns the budget Verdict; rejected messages are logged
        (verbatim, with size) so the harness can report them; never raised."""
        if sender not in self.seats:
            raise ValueError(f"sender {sender!r} is not a seat")

        if self.topology == "common":
            rcpts = tuple(s for s in self.seats if s != sender)
            v = check(text, self.cap)
            if v.ok:
                msg = Message(round_sent, sender, rcpts, text)
                self._pending.append(msg); self.admitted.append(msg)
            else:
                self.rejections.append(
                    Rejection(round_sent, sender, "over_cap",
                              f"bus post>{self.cap}b" if self.cap else "bus post", v.bits, text))
            return v

        # mesh: recipients required, one verdict per dyad; the caller sees the worst
        if not recipients:
            raise ValueError("mesh send requires explicit recipients")
        worst: Optional[Verdict] = None
        for r in recipients:
            if r not in self.seats or r == sender:
                self.rejections.append(
                    Rejection(round_sent, sender, "unknown_recipient", r, 0, text))
                continue
            v = check(text, self.cap)  # PER-DYAD cap — same text priced on each link
            if v.ok:
                msg = Message(round_sent, sender, (r,), text)
                self._pending.append(msg); self.admitted.append(msg)
            else:
                self.rejections.append(
                    Rejection(round_sent, sender, "over_cap", f"dyad {sender}->{r}", v.bits, text))
            if worst is None or (not v.ok):
                worst = v
        return worst if worst is not None else check("", 0)

    # ---- delivery ---------------------------------------------------------
    def advance_round(self) -> None:
        """Move pending messages into recipients' inboxes. Call once per round."""
        for msg in self._pending:
            for r in msg.recipients:
                self._delivered[r].append(msg)
        self._pending = []

    def inbox(self, seat: str) -> List[Message]:
        """All messages delivered to `seat` so far (across rounds). Read-only."""
        if seat not in self.seats:
            raise ValueError(f"no such seat {seat!r}")
        return list(self._delivered[seat])

    # ---- accounting -------------------------------------------------------
    def total_admitted_bits(self) -> int:
        return sum(m.bits for m in self.admitted)
