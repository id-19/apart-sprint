"""scenario.py — the scenario-agnostic contract.

The engine, tools, comms, recorder, and model client know only this interface.
A scenario owns its prompts, world, observations, action tools, settlement,
harm/Q, anchors, and detector binning.  It contains no engine mechanics.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .tools import ToolSpec


@dataclass
class Policy:
    """A scripted anchor decision.

    ``decide(seat, cycle)`` returns ``{"name": tool, "arguments": {...}}`` or
    ``None`` to do nothing.  It is used only by the no-model test ladder.
    """
    decide: Callable[[str, int], dict | None]


class Scenario:
    name = "scenario"
    version = "0"
    default_seats = 4
    cycles = 8
    default_step = 50.0

    def docs_dir(self) -> Path | None:
        return None

    def desk_files(self, world: Any, seat: str) -> dict[str, str]:
        """Files placed in the seat's private folder before the first cycle."""
        return {}

    def system_prompt(self, world: Any, seat: str) -> str:
        raise NotImplementedError

    def make_world(self, seats: list[str], seed: int) -> Any:
        raise NotImplementedError

    def new_round(self, world: Any, cycle: int) -> None:
        raise NotImplementedError

    def warmup(self, world: Any, seats: list[str]) -> None:
        """Settle a plausible prior cycle before cycle 1."""

    def observation(self, world: Any, seat: str, cycle: int) -> dict:
        raise NotImplementedError

    def render(self, world: Any, seat: str, obs: dict, inbox: list,
               exchange: int, max_exchanges: int, remaining_bytes: int) -> str:
        raise NotImplementedError

    def render_update(self, world: Any, seat: str, obs: dict, new_messages: list,
                      exchange: int, max_exchanges: int,
                      remaining_bytes: int) -> str:
        """Text appended for exchanges after the first.  Default is neutral."""
        lines = [f"Exchange {exchange} of {max_exchanges}."]
        if exchange >= max_exchanges:
            lines.append("This is the final exchange. Only the filing tools are "
                         "available now; file your action.")
        if new_messages:
            lines.append("New messages this cycle:")
            for m in new_messages:
                lines.append(f"- from {m.sender}: {m.text}")
        else:
            lines.append("No new messages.")
        lines.append(f"Transmission allowance left: {remaining_bytes} bytes.")
        return "\n".join(lines)

    def scalar(self, world: Any) -> float:
        raise NotImplementedError

    def action_tools(self, world: Any, seat: str) -> list[ToolSpec]:
        raise NotImplementedError

    def apply_action(self, world: Any, seat: str, action: dict) -> None:
        world.setdefault("actions", {})[seat] = action

    def settle(self, world: Any) -> dict:
        raise NotImplementedError

    def bin_action(self, action: dict | None) -> str:
        return "NONE" if action is None else str(action)

    def harm(self, record: dict) -> float:
        return float(record.get("harm", 0.0))

    def q(self, record: dict, world: Any) -> float:
        denom = float(record.get("optimal_profit", 0.0))
        return max(0.0, min(1.0, float(record.get("coalition_profit", 0.0)) / denom)) \
            if denom > 0 else 0.0

    def anchors(self, seats: list[str], seed: int) -> dict[str, Policy]:
        raise NotImplementedError


def load_scenario(name: str) -> Scenario:
    aliases = {"s1": "s1", "s1_procurement": "s1", "s2": "s2",
               "s2_trading": "s2", "s3": "s3", "s3_rating": "s3",
               "s4": "s4", "s4_bridge": "s4"}
    module = aliases.get(name, name)
    mod = importlib.import_module(f"{__package__}.scenarios.{module}")
    scenario = getattr(mod, "SCENARIO", None)
    if scenario is None:
        raise ImportError(f"{module} exports no SCENARIO")
    return scenario
