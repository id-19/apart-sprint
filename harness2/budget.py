"""budget.py — per-channel message budget. Pure functions, no I/O (R3).

One pre-registered bit definition used everywhere (ladder labels, residual printouts):
    bits(text) = len(text.encode("utf-8")) * 8

Semantics (design §2.1 / §4.2.1):
  * the cap is per channel per round — a channel is the common bus, or one dyad under mesh;
  * an over-cap message is REJECTED IN FULL, never truncated. Truncation would silently
    convert "no budget" into a different, uncontrolled budget;
  * this module only judges size. The engine owns logging of rejected/dropped messages.
"""

from __future__ import annotations


def count_bits(text: str) -> int:
    """Bits carried by `text` under the sprint's single pre-registered definition.

    UTF-8 byte length × 8. Chars outside ASCII cost >8 bits each, which is correct:
    the cap is on information actually transmitted, not on glyphs.
    """
    if not isinstance(text, str):
        raise TypeError(f"count_bits expects str, got {type(text).__name__}")
    return len(text.encode("utf-8")) * 8


def count_bytes(text: str) -> int:
    """Byte length, for size logs on rejected messages."""
    return len(text.encode("utf-8"))


class Verdict:
    """Result of checking one message against one channel's cap."""

    __slots__ = ("ok", "bits", "cap")

    def __init__(self, ok: bool, bits: int, cap: int) -> None:
        self.ok = ok
        self.bits = bits
        self.cap = cap

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        status = "ADMIT" if self.ok else "REJECT"
        return f"Verdict({status}, {self.bits}/{self.cap} bits)"


def check(text: str, cap_bits: "int | None") -> Verdict:
    """Judge one message against one channel's per-round cap.

    Returns admit/reject only; never mutates the text. A cap of None means
    uncapped (the 16_000 rung's 'effectively unlimited for a single channel'
    is still a finite cap at the ladder level — None is for engine-internal
    scripted messages, not an agent arm).
    """
    if cap_bits is not None and cap_bits < 0:
        raise ValueError("cap_bits must be >= 0 or None")
    n = count_bits(text)
    ok = cap_bits is None or n <= cap_bits
    return Verdict(ok=ok, bits=n, cap=cap_bits if cap_bits is not None else -1)
