"""Unit tests for tools.py (sandbox scope). Run: python3 harness2/test_tools.py"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import FileTools  # noqa: E402


def _setup():
    tmp = tempfile.mkdtemp(prefix="apt_tools_")
    run_dir = os.path.join(tmp, "run_cell_1")
    os.makedirs(run_dir)

    # a "reference" file the scenario whitelists
    ref = os.path.join(tmp, "reference.md")
    with open(ref, "w") as f:
        f.write("REFERENCE DATA")

    # an out-of-scope file that must never be readable
    secret = os.path.join(tmp, "secret.txt")
    with open(secret, "w") as f:
        f.write("SHOULD NOT BE READABLE")

    return tmp, run_dir, ref, secret


def test_write_and_read_back_inside_run_dir() -> None:
    tmp, run_dir, ref, secret = _setup()
    ft = FileTools(run_dir, read_whitelist=[ref])
    w = ft.write_file("notes/plan.md", "hold price 13")
    assert w.ok and w.path.startswith(os.path.realpath(run_dir))
    r = ft.read_file("notes/plan.md")
    assert r.ok and r.content == "hold price 13"


def test_write_escaping_run_dir_is_refused() -> None:
    tmp, run_dir, ref, secret = _setup()
    ft = FileTools(run_dir, read_whitelist=[ref])
    for bad in ("../evil.txt", "../../evil.txt", os.path.join(tmp, "evil.txt")):
        w = ft.write_file(bad, "x")
        assert not w.ok and "escape" in w.error.lower(), bad
    # nothing was written outside
    assert not os.path.exists(os.path.join(tmp, "evil.txt"))


def test_read_whitelist_allowed() -> None:
    tmp, run_dir, ref, secret = _setup()
    ft = FileTools(run_dir, read_whitelist=[ref])
    r = ft.read_file(ref)
    assert r.ok and r.content == "REFERENCE DATA"


def test_read_outside_scope_is_refused_even_if_file_exists() -> None:
    tmp, run_dir, ref, secret = _setup()
    ft = FileTools(run_dir, read_whitelist=[ref])
    r = ft.read_file(secret)
    assert not r.ok and "not allowed" in r.error.lower()
    # path-relative variant also refused
    r2 = ft.read_file("../secret.txt")
    assert not r2.ok


def test_symlink_cannot_escape_scope() -> None:
    tmp, run_dir, ref, secret = _setup()
    ft = FileTools(run_dir, read_whitelist=[ref])
    link = os.path.join(run_dir, "escape_link")
    os.symlink(secret, link)           # symlink inside run_dir → outside file
    r = ft.read_file("escape_link")
    assert not r.ok                    # realpath resolution rejects it


def test_missing_file_read_is_clean_error_not_exception() -> None:
    tmp, run_dir, ref, secret = _setup()
    ft = FileTools(run_dir, read_whitelist=[ref])
    r = ft.read_file("no_such_file.md")
    assert not r.ok and r.error        # returned, not raised


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
