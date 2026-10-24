"""Unit tests for ollama_client.py — transport/seed/logging/INFRA (R5, R6, R9).
Run: python3 harness2/test_ollama_client.py  (no server needed; transport is scripted)
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ollama_client import OllamaClient, TransportCollapse  # noqa: E402


def _client(tmp, transport):
    return OllamaClient(run_dir=tmp, cell="test_cell", model="dummy:0b",
                        seed=11, transport=transport)


def test_seed_and_options_are_in_the_payload() -> None:
    seen = {}

    def transport(payload):
        seen.update(payload)
        return {"message": {"content": "OK"}}

    tmp = tempfile.mkdtemp()
    c = _client(tmp, transport)
    rec = c.chat(system="SYS", user="hi", seat="A", round=0)
    assert rec.status == "ok" and rec.response == "OK"
    assert seen["options"]["seed"] == 11
    assert seen["think"] is False and seen["stream"] is False
    assert "response_format" not in seen and "format" not in seen  # no JSON mode


def test_every_call_logged_verbatim_and_flushed() -> None:
    tmp = tempfile.mkdtemp()
    c = _client(tmp, lambda p: {"message": {"content": "resp"}})
    for r in range(3):
        c.chat(system="S", user=f"u{r}", seat="B", round=r)
    with open(os.path.join(tmp, "raw_calls.jsonl")) as f:
        lines = [json.loads(x) for x in f if x.strip()]
    assert len(lines) == 3
    assert lines[1]["user"] == "u1" and lines[1]["seed"] == 11
    assert all(x["status"] == "ok" for x in lines)


def test_transport_failure_is_infra_not_malformed_and_aborts() -> None:
    import urllib.error

    def dead(payload):
        raise urllib.error.URLError("Connection refused")

    tmp = tempfile.mkdtemp()
    c = _client(tmp, dead)
    collapsed = False
    try:
        c.chat(system="S", user="u", seat="A", round=0)  # 1 call → 4 attempts → collapse
    except TransportCollapse:
        collapsed = True
    assert collapsed
    with open(os.path.join(tmp, "raw_calls.jsonl")) as f:
        lines = [json.loads(x) for x in f if x.strip()]
    assert len(lines) == 1 and lines[0]["status"] == "infra"
    assert "refused" in lines[0]["error"] or "transport" in lines[0]["error"]


def test_retries_then_recovers_within_limit() -> None:
    attempts = {"n": 0}

    def flaky(payload):
        attempts["n"] += 1
        if attempts["n"] < 2:
            import urllib.error
            raise urllib.error.URLError("blip")
        return {"message": {"content": "recovered"}}

    tmp = tempfile.mkdtemp()
    c = _client(tmp, flaky)
    rec = c.chat(system="S", user="u", seat="A", round=0)
    assert rec.status == "ok" and rec.response == "recovered"
    assert attempts["n"] == 2  # retried, then succeeded


def test_memory_sample_line_written() -> None:
    tmp = tempfile.mkdtemp()
    c = _client(tmp, lambda p: {"message": {"content": "x"}})
    c.chat(system="S", user="u", seat="A", round=0)
    mp = os.path.join(tmp, "memory.jsonl")
    assert os.path.exists(mp)
    with open(mp) as f:
        rec = json.loads(f.readline())
    assert ("our_rss_mb" in rec) or ("error" in rec)  # never crashes the run


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
