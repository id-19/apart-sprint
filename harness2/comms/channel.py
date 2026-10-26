"""comms/channel.py — one transferable transmission allowance per seat per cycle.

The unit used by the world is characters of text, one byte each for the ASCII
the seats write.  The experiment's ladder is stored in those same characters:
a rung of 128 is 128 characters per seat per cycle.  A seat's allowance is
``rung * N`` for the whole cycle, not per exchange and not per channel.
A forum post is charged once.  A direct message to k desks is charged k times.
An over-allowance message is rejected whole and not debited; nothing is ever
truncated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def text_bytes(text: str) -> int:
    # Charged in characters so the allowance the desk reads is the same unit
    # it writes in; the experiment's bit ladder maps at 8 bits per character.
    return len(text)


@dataclass
class Message:
    cycle: int
    exchange: int
    sender: str
    recipients: tuple[str, ...]
    text: str
    channel: str = "common_room"     # "common_room" or "direct"

    @property
    def bytes(self) -> int:
        return text_bytes(self.text)

    @property
    def bits(self) -> int:
        return self.bytes * 8


@dataclass
class SendResult:
    ok: bool
    reason: str
    cost: int
    remaining: int
    message: Message | None = None
    recipients: tuple[str, ...] = ()
    # A rejected message is still a message the seat tried to send, so the
    # text is kept for the record even though nothing was transmitted.
    text: str = ""
    channel: str = ""

    def render(self) -> str:
        if not self.ok:
            return (f"Not sent: {self.reason}. Your line is unchanged "
                    f"({self.remaining} characters left this window).")
        return (f"Note passed to {', '.join(self.recipients)} ({self.cost} characters). "
                f"{self.remaining} characters left on your line this window.")


class RoundLedger:
    """The whole cycle's message ledger for one cell."""

    def __init__(self, seats: Iterable[str], allowance_bytes: int, cycle: int) -> None:
        self.seats = tuple(seats)
        if len(set(self.seats)) != len(self.seats):
            raise ValueError("seat labels must be unique")
        if allowance_bytes < 0:
            raise ValueError("allowance must be >= 0")
        self.allowance = int(allowance_bytes)
        self.cycle = int(cycle)
        self.remaining = {s: self.allowance for s in self.seats}
        self.pending: list[Message] = []
        self.inboxes: dict[str, list[Message]] = {s: [] for s in self.seats}
        self.admitted: list[Message] = []
        self.rejected: list[SendResult] = []
        self._exchange = 0

    @property
    def enabled(self) -> bool:
        return self.allowance > 0 and len(self.seats) > 1

    def set_exchange(self, exchange: int) -> None:
        self._exchange = int(exchange)

    def _accept(self, sender: str, recipients: tuple[str, ...], text: str,
                cost: int, channel: str) -> SendResult:
        if cost > self.remaining[sender]:
            r = SendResult(False, "it is longer than the allowance you have left",
                           cost, self.remaining[sender], recipients=recipients,
                           text=text, channel=channel)
            self.rejected.append(r)
            return r
        self.remaining[sender] -= cost
        msg = Message(self.cycle, self._exchange, sender, recipients, text,
                      channel=channel)
        self.pending.append(msg)
        self.admitted.append(msg)
        return SendResult(True, "", cost, self.remaining[sender], msg,
                          recipients, channel=channel)

    def post(self, sender: str, text: str) -> SendResult:
        if sender not in self.remaining:
            raise ValueError(f"unknown sender {sender!r}")
        recipients = tuple(s for s in self.seats if s != sender)
        return self._accept(sender, recipients, text, text_bytes(text),
                            "common_room")

    def dm(self, sender: str, recipients: list[str], text: str) -> SendResult:
        if sender not in self.remaining:
            raise ValueError(f"unknown sender {sender!r}")
        clean = tuple(dict.fromkeys(r for r in recipients if r != sender))
        if not clean:
            r = SendResult(False, "no valid recipient was named", 0,
                           self.remaining[sender], text=text, channel="direct")
            self.rejected.append(r)
            return r
        unknown = [r for r in clean if r not in self.remaining]
        if unknown:
            r = SendResult(False, f"unknown desk {unknown[0]!r}", 0,
                           self.remaining[sender], recipients=clean, text=text,
                           channel="direct")
            self.rejected.append(r)
            return r
        cost = text_bytes(text) * len(clean)
        return self._accept(sender, clean, text, cost, "direct")

    def deliver(self) -> None:
        """Make this exchange's admitted messages visible to recipients."""
        for msg in self.pending:
            for r in msg.recipients:
                self.inboxes[r].append(msg)
        self.pending = []

    def inbox(self, seat: str) -> list[Message]:
        return list(self.inboxes[seat])

    def total_admitted_bytes(self) -> int:
        return sum(m.bytes for m in self.admitted)
