"""runner.py — the single entry point for one cell.

    run_scenario(s1, seed=0, rung=2048, model="gemma4:cloud")

Common arguments are the harness's own: seed, steps, seats, rung, model
options, output directory, exchange clock.  Everything else is passed through
untouched to the scenario's ``create_world``, so a scenario's parameters never
appear in the harness — a scenario that takes none rejects an unknown keyword
loudly rather than ignoring it.  Those kwargs are recorded in the summary, and
the matrix's resume skips a cell only when they match.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import CellSpec, allocate_run_dir, num_ctx_for
from .engine import Engine
from .model import ModelClient
from .record import Recorder
from .scenario import Scenario


def run_scenario(
    scenario: Scenario,
    *,
    seed: int = 0,
    steps: int | None = None,
    seats: int | None = None,
    rung: int = 0,
    model: str = "scripted",
    temperature: float = 1.0,
    think: bool | None = False,
    num_ctx: int | None = None,
    num_predict: int = 4096,
    max_exchanges: int | None = None,
    out_dir: str | Path = "runs",
    transport=None,
    **scenario_kwargs: Any,
) -> dict:
    """Run one cell and return its summary."""
    n = int(seats or scenario.default_seats)
    names = [chr(ord("A") + i) for i in range(n)]
    cell = CellSpec(scenario.name, int(rung), n, int(seed), tuple(names))
    run_dir = allocate_run_dir(Path(out_dir), cell.cell_id)
    ctx = int(num_ctx or num_ctx_for(n))
    recorder = Recorder(run_dir, {**cell.as_dict(),
                                  "scenario_kwargs": scenario_kwargs})
    client = ModelClient(
        run_dir=run_dir, cell_id=cell.cell_id, model=model,
        think=think, temperature=temperature, num_ctx=ctx,
        seed=seed, transport=transport,
    )
    engine = Engine(
        cell=cell, scenario=scenario, cell_dir=run_dir, client=client,
        recorder=recorder,
        max_exchanges=int(max_exchanges or scenario.exchanges or 6),
        num_ctx=ctx, num_predict=num_predict,
        cycles=steps,
        scenario_kwargs=scenario_kwargs,
    )
    return engine.run()
