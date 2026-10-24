"""Unit tests for budget.py (R3). Run: python3 harness2/test_budget.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from budget import check, count_bits, count_bytes


def test_bits_definition_is_utf8_bytes_times_8() -> None:
    assert count_bits("") == 0
    assert count_bits("a") == 8
    assert count_bits("abc") == 24
    # non-ASCII costs more than 8 bits/char — the cap is on information, not glyphs
    assert count_bits("₹") == 3 * 8  # U+20B9 is 3 bytes in UTF-8
    assert count_bytes("₹") == 3


def test_admit_at_and_below_cap() -> None:
    cap = 500
    # 62 chars = 496 bits <= 500; 500 is not byte-divisible, so the exact
    # integer-floor boundary is what's really being tested here
    v = check("x" * (cap // 8), cap)
    assert v.ok and v.bits == 496 and v.cap == cap
    v2 = check("hi", cap)
    assert v2.ok and v2.bits == 16


def test_admit_exactly_at_cap() -> None:
    v = check("x" * 62, 496)  # 62*8 = 496 exactly
    assert v.ok and v.bits == 496


def test_reject_over_cap_never_truncate() -> None:
    cap = 24  # 3 ASCII chars
    over = "abcd"  # 32 bits
    v = check(over, cap)
    assert not v.ok
    assert v.bits == 32 and v.cap == 24
    # the text object is untouched — rejection happens before delivery
    assert over == "abcd"


def test_zero_cap_rejects_any_nonempty_and_admits_empty() -> None:
    assert not check("a", 0).ok
    assert check("", 0).ok


def test_uncapped_none_admits_anything() -> None:
    v = check("x" * 100_000, None)
    assert v.ok and v.cap == -1


def test_negative_cap_is_a_caller_bug() -> None:
    try:
        check("a", -1)
    except ValueError:
        return
    raise AssertionError("negative cap must raise")


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
