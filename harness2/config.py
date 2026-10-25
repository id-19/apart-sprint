"""config.py — experiment configuration, cells, schedule and approval hashes.

The config is the only place axes live. The engine, scenarios and recorder never
read `experiment.json` directly; `entry.py` resolves it once and hands the engine
a `CellSpec`.

Structural rules enforced here (not in the engine):
  * S4 is role-fixed at N=3.
  * N=1 runs only the rungs in `n1_rungs` (default [0]).
  * Every scenario's cell list is the cross product of its N values, rungs and seeds.
  * Cell ids are unique; a rerun gets a new run directory, never an overwrite.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_RUNGS = (0, 512, 2048, 8192)
DEFAULT_N = (1, 4, 12)
DEFAULT_SEEDS = tuple(range(10))
DEFAULT_SCENARIOS = ("s1", "s2", "s3", "s4")
SCENARIO_N_FIXED = {"s4": 3}
SCENARIO_CYCLES = {"s1": 8, "s2": 10, "s3": 8, "s4": 8}
N1_RUNGS = (0,)


class ConfigError(ValueError):
    """A config that cannot produce a valid cell list."""


class PlanMismatch(ValueError):
    """The approved plan does not match the current config or schedule."""


@dataclass(frozen=True)
class CellSpec:
    scenario: str
    rung: int
    n: int
    seed: int
    seats: tuple[str, ...]

    @property
    def cell_id(self) -> str:
        return f"{self.scenario}_n{self.n}_b{self.rung}_s{self.seed}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "scenario": self.scenario,
            "rung": self.rung,
            "n": self.n,
            "seed": self.seed,
            "seats": list(self.seats),
        }


def seats(n: int) -> tuple[str, ...]:
    """Seat labels A.. for N seats. Refuses N > 26 so labels stay unambiguous."""
    if not isinstance(n, int) or n < 1:
        raise ConfigError(f"N must be a positive integer, got {n!r}")
    if n > 26:
        raise ConfigError(f"N={n} exceeds the 26 single-letter seat labels")
    return tuple(chr(ord("A") + i) for i in range(n))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _as_int_list(value: Any, name: str) -> tuple[int, ...]:
    _require(isinstance(value, list) and value, f"{name} must be a non-empty list")
    out: list[int] = []
    for item in value:
        _require(isinstance(item, int) and not isinstance(item, bool),
                 f"{name} must contain integers, got {item!r}")
        out.append(item)
    _require(len(set(out)) == len(out), f"{name} has duplicates: {value!r}")
    return tuple(out)


def _as_str_list(value: Any, name: str) -> tuple[str, ...]:
    _require(isinstance(value, list) and value, f"{name} must be a non-empty list")
    out: list[str] = []
    for item in value:
        _require(isinstance(item, str) and item, f"{name} must contain non-empty strings")
        out.append(item)
    _require(len(set(out)) == len(out), f"{name} has duplicates: {value!r}")
    return tuple(out)


@dataclass(frozen=True)
class Config:
    path: Path
    raw: Mapping[str, Any]

    # ---- accessors -----------------------------------------------------
    @property
    def version(self) -> int:
        return int(self.raw.get("version", 0))

    @property
    def name(self) -> str:
        return str(self.raw.get("name", "unnamed"))

    @property
    def model(self) -> Mapping[str, Any]:
        model = self.raw.get("model")
        _require(isinstance(model, Mapping), "model must be an object")
        return model

    @property
    def model_name(self) -> str:
        return str(self.model.get("name", ""))

    @property
    def model_provider(self) -> str:
        return str(self.model.get("provider", "ollama"))

    @property
    def think(self) -> bool:
        return bool(self.model.get("think", True))

    @property
    def temperature(self) -> float:
        return float(self.model.get("temperature", 0.7))

    @property
    def num_predict_comm(self) -> int:
        return int(self.model.get("num_predict_comm", 512))

    @property
    def num_predict_action(self) -> int:
        return int(self.model.get("num_predict_action", 256))

    @property
    def axes(self) -> Mapping[str, Any]:
        axes = self.raw.get("axes")
        _require(isinstance(axes, Mapping), "axes must be an object")
        return axes

    @property
    def rungs(self) -> tuple[int, ...]:
        return _as_int_list(list(self.axes.get("rungs", [])), "axes.rungs")

    @property
    def n_values(self) -> tuple[int, ...]:
        return _as_int_list(list(self.axes.get("n", [])), "axes.n")

    @property
    def seeds(self) -> tuple[int, ...]:
        return _as_int_list(list(self.axes.get("seeds", [])), "axes.seeds")

    @property
    def scenarios(self) -> tuple[str, ...]:
        return _as_str_list(list(self.raw.get("scenarios", [])), "scenarios")

    @property
    def scenario_n(self) -> Mapping[str, int]:
        value = self.raw.get("scenario_n", {})
        _require(isinstance(value, Mapping), "scenario_n must be an object")
        out: dict[str, int] = {}
        for key, item in value.items():
            _require(isinstance(key, str), "scenario_n keys must be strings")
            _require(isinstance(item, int) and not isinstance(item, bool) and item >= 1,
                     f"scenario_n[{key!r}] must be a positive integer")
            out[key] = item
        return out

    @property
    def n1_rungs(self) -> tuple[int, ...]:
        value = self.raw.get("n1_rungs", list(N1_RUNGS))
        return _as_int_list(list(value), "n1_rungs")

    @property
    def max_turns(self) -> int:
        turns = self.raw.get("turns", {})
        _require(isinstance(turns, Mapping), "turns must be an object")
        value = turns.get("max", 6)
        _require(isinstance(value, int) and not isinstance(value, bool) and value >= 1,
                 "turns.max must be a positive integer")
        return value

    @property
    def comms(self) -> Mapping[str, Any]:
        comms = self.raw.get("comms", {})
        _require(isinstance(comms, Mapping), "comms must be an object")
        return comms

    @property
    def runs_dir(self) -> Path:
        paths = self.raw.get("paths", {})
        _require(isinstance(paths, Mapping), "paths must be an object")
        return Path(str(paths.get("runs", "runs")))

    # ---- validation ----------------------------------------------------
    def validate(self, *, for_run: bool = False) -> None:
        _require(self.version == 1, f"unsupported config version {self.version!r}")
        _require(self.model_name != "", "model.name is empty")
        if for_run:
            _require(self.model_name.upper() != "TBD",
                     "model.name is TBD; select the cheapest tool-capable Ollama model first")
        _require(self.model_provider == "ollama",
                 f"only the ollama provider is supported, got {self.model_provider!r}")
        _require(0.0 <= self.temperature <= 2.0,
                 f"model.temperature out of range: {self.temperature!r}")
        _require(self.num_predict_comm >= 1 and self.num_predict_action >= 1,
                 "num_predict values must be positive")

        _require(self.rungs == tuple(sorted(self.rungs)),
                 f"axes.rungs must be ascending, got {self.rungs!r}")
        _require(all(r >= 0 for r in self.rungs), "axes.rungs must be non-negative")
        _require(0 in self.rungs, "axes.rungs must include 0 (the 0* baseline)")
        _require(all(n >= 1 for n in self.n_values), "axes.n must be positive")
        _require(all(s >= 0 for s in self.seeds), "axes.seeds must be non-negative")
        _require(self.max_turns >= 1, "turns.max must be >= 1")

        unknown = [s for s in self.scenarios if s not in DEFAULT_SCENARIOS]
        _require(not unknown, f"unknown scenarios: {unknown!r}")

        for scenario, n in self.scenario_n.items():
            _require(scenario in self.scenarios,
                     f"scenario_n names {scenario!r}, which is not in scenarios")
            _require(scenario in SCENARIO_N_FIXED,
                     f"scenario_n is only for role-fixed scenarios; {scenario!r} is on the N axis")
        for scenario, n in SCENARIO_N_FIXED.items():
            if scenario in self.scenarios:
                configured = self.scenario_n.get(scenario, n)
                _require(configured == n,
                         f"{scenario} is role-fixed at N={n}, got {configured}")

        _require(set(self.n1_rungs).issubset(set(self.rungs)),
                 f"n1_rungs {self.n1_rungs!r} must be a subset of axes.rungs {self.rungs!r}")
        _require(self.n1_rungs == N1_RUNGS,
                 f"N=1 may run only rung 0*, got n1_rungs={self.n1_rungs!r}")

    def validate_selected(self) -> None:
        """Checks that depend on which scenarios were selected."""
        for scenario in self.scenarios:
            if scenario in SCENARIO_N_FIXED:
                continue
            _require(1 in self.n_values or 4 in self.n_values or 12 in self.n_values,
                     f"{scenario} has no N value")

    # ---- cells ---------------------------------------------------------
    def cells(self) -> tuple[CellSpec, ...]:
        self.validate()
        out: list[CellSpec] = []
        for scenario in self.scenarios:
            if scenario in SCENARIO_N_FIXED:
                ns: tuple[int, ...] = (SCENARIO_N_FIXED[scenario],)
            else:
                ns = self.n_values
            for n in ns:
                rungs = self.n1_rungs if n == 1 else self.rungs
                for rung in rungs:
                    for seed in self.seeds:
                        out.append(CellSpec(
                            scenario=scenario,
                            rung=rung,
                            n=n,
                            seed=seed,
                            seats=seats(n),
                        ))
        self._unique_cell_ids(out)
        return tuple(out)

    def schedule(self) -> tuple[CellSpec, ...]:
        """Deterministic interleaving of the cell list.

        Provider drift must not look like a dose-response. The shuffle is seeded by
        the scientific config hash, so the same config always yields the same order,
        and the order is committed in `plan.json`.
        """
        cells = list(self.cells())
        rng = random.Random(f"{self.config_hash()}:schedule")
        rng.shuffle(cells)
        return tuple(cells)

    @staticmethod
    def _unique_cell_ids(cells: Iterable[CellSpec]) -> None:
        seen: set[str] = set()
        for cell in cells:
            if cell.cell_id in seen:
                raise ConfigError(f"duplicate cell id {cell.cell_id!r}")
            seen.add(cell.cell_id)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cell in self.cells():
            counts[cell.scenario] = counts.get(cell.scenario, 0) + 1
        return counts

    # ---- hashes --------------------------------------------------------
    def scientific_payload(self) -> dict[str, Any]:
        """What an approval covers: axes, model behaviour, turn/comms policy.

        Excludes output paths, spend limits, and price metadata. Those can change
        without invalidating the science plan; a model or axis change cannot.
        """
        return {
            "version": self.version,
            "name": self.name,
            "model": {
                "name": self.model_name,
                "provider": self.model_provider,
                "think": self.think,
                "temperature": self.temperature,
                "num_predict_comm": self.num_predict_comm,
                "num_predict_action": self.num_predict_action,
            },
            "axes": {
                "rungs": list(self.rungs),
                "n": list(self.n_values),
                "seeds": list(self.seeds),
            },
            "scenarios": list(self.scenarios),
            "scenario_n": dict(self.scenario_n),
            "n1_rungs": list(self.n1_rungs),
            "turns": {"max": self.max_turns},
            "comms": dict(self.comms),
        }

    def config_hash(self) -> str:
        return _hash(self.scientific_payload())

    def schedule_hash(self) -> str:
        return _hash([cell.as_dict() for cell in self.schedule()])

    # ---- plan ----------------------------------------------------------
    def plan(self) -> dict[str, Any]:
        cells = self.schedule()
        counts = self.counts()
        calls_min = sum(cell.n * SCENARIO_CYCLES[cell.scenario] for cell in cells)
        calls_max = sum(cell.n * self.max_turns * SCENARIO_CYCLES[cell.scenario]
                        for cell in cells)
        return {
            "generated_at": _now_iso(),
            "config_path": str(self.path),
            "config_hash": self.config_hash(),
            "schedule_hash": self.schedule_hash(),
            "model": {
                "name": self.model_name,
                "provider": self.model_provider,
                "think": self.think,
            },
            "counts": counts,
            "cycles": dict(SCENARIO_CYCLES),
            "total_cells": len(cells),
            "calls_min": calls_min,
            "calls_max": calls_max,
            "cells": [cell.as_dict() for cell in cells],
        }

    def write_plan(self, path: Path) -> dict[str, Any]:
        plan = self.plan()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return plan

    def verify_plan(self, plan_path: Path) -> dict[str, Any]:
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PlanMismatch(f"approval plan not found: {plan_path}") from exc
        except json.JSONDecodeError as exc:
            raise PlanMismatch(f"approval plan is not valid JSON: {plan_path}: {exc}") from exc
        if plan.get("config_hash") != self.config_hash():
            raise PlanMismatch(
                "approval plan was generated from a different scientific config; "
                "run `entry.py plan` again and review the new cell list"
            )
        if plan.get("schedule_hash") != self.schedule_hash():
            raise PlanMismatch(
                "approval plan's schedule does not match the current cell order; "
                "run `entry.py plan` again"
            )
        return plan


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ConfigError("config root must be an object")
    config = Config(path=path, raw=raw)
    config.validate()
    return config


def allocate_run_dir(root: str | Path, prefix: str) -> Path:
    """Return a fresh run directory. Never reuse or overwrite an existing one."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = root / _safe_name(prefix)
    if not base.exists():
        return base
    for attempt in range(2, 1000):
        candidate = root / f"{_safe_name(prefix)}_a{attempt}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not allocate a fresh run directory under {root}")


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(value: str) -> str:
    cleaned = _SAFE.sub("-", value).strip("-")
    if not cleaned:
        raise ConfigError("run prefix is empty after sanitising")
    return cleaned


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
