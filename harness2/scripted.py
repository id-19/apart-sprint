"""scripted.py — no-model transports for the unit, anchor, and dummy ladder.

The transport has the same shape as Ollama's chat response.  It is used only
with the engine's scripted path; live cells use ``ModelClient`` with no
transport override.
"""

from __future__ import annotations

from typing import Callable

from .scenario import Policy


def transport_for(policy: Policy) -> Callable[[dict, dict], dict]:
    def transport(payload: dict, meta: dict) -> dict:
        seat = meta.get("seat", "")
        cycle = int(meta.get("cycle", 0))
        decision = policy.decide(seat, cycle)
        if decision is None:
            return {"message": {"role": "assistant", "content": ""}, "model": "scripted"}
        decisions = decision if isinstance(decision, list) else [decision]
        calls = [{"function": {"name": d["name"], "arguments": d.get("arguments", {})}}
                 for d in decisions]
        return {"message": {"role": "assistant", "content": "", "tool_calls": calls},
                "model": "scripted"}

    return transport


def fixed_tool(name: str, arguments: dict | None = None) -> Policy:
    return Policy(lambda seat, cycle: {"name": name, "arguments": arguments or {}})


def fixed_tool_per_seat(build: Callable[[str, int], dict]) -> Policy:
    return Policy(lambda seat, cycle: build(seat, cycle))


def no_action() -> Policy:
    return Policy(lambda seat, cycle: None)
