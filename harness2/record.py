"""record.py — append-only per-cell records.

Nothing here rewrites an earlier line.  Each file is opened in append mode and
flushed after every record, so a crashed cell still leaves its partial data.
A new attempt gets a new directory (``allocate_run_dir``); an existing cell
directory is never reopened for writing.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class Recorder:
    FILES = ("raw_calls", "messages", "trajectory", "settlement", "live_flags")

    def __init__(self, cell_dir: str | os.PathLike, spec: dict) -> None:
        self.dir = Path(cell_dir).resolve()
        if (self.dir / "cell.json").exists():
            raise FileExistsError(f"cell directory already written: {self.dir}")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.spec = dict(spec)
        self.cell_id = self.spec.get("cell_id", self.dir.name)
        (self.dir / "cell.json").write_text(
            json.dumps(self.spec, indent=2, sort_keys=True), encoding="utf-8")
        self._files = {name: open(self.dir / f"{name}.jsonl", "a",
                                  encoding="utf-8", buffering=1)
                       for name in self.FILES}
        self._transcript = open(self.dir / "transcript.md", "a",
                                encoding="utf-8", buffering=1)
        self._closed = False

    # -- low level ---------------------------------------------------------
    def _line(self, name: str, record: dict) -> None:
        if self._closed:
            raise RuntimeError("recorder is closed")
        base = {"cell_id": self.cell_id,
                "scenario": self.spec.get("scenario"),
                "rung": self.spec.get("rung"),
                "n": self.spec.get("n"),
                "seed": self.spec.get("seed"),
                "ts": time.time()}
        base.update(record)
        self._files[name].write(json.dumps(base, ensure_ascii=False) + "\n")
        self._files[name].flush()

    def raw_call(self, record: dict) -> None:
        self._line("raw_calls", record)

    def message(self, record: dict) -> None:
        self._line("messages", record)

    def trajectory(self, record: dict) -> None:
        self._line("trajectory", record)

    def settlement(self, record: dict) -> None:
        self._line("settlement", record)

    def flag(self, record: dict) -> None:
        self._line("live_flags", record)

    # -- human-readable transcript ----------------------------------------
    def transcript(self, text: str) -> None:
        self._transcript.write(text.rstrip() + "\n\n")
        self._transcript.flush()

    def section(self, title: str) -> None:
        self.transcript(f"\n## {title}\n")

    # -- end of cell -------------------------------------------------------
    def write_summary(self, summary: dict) -> None:
        path = self.dir / "summary.json"
        if path.exists():
            raise FileExistsError(f"summary already written: {path}")
        path.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8")

    def write_meta_flags(self, flags: dict) -> None:
        path = self.dir / "meta_flags.json"
        if path.exists():
            raise FileExistsError(f"meta flags already written: {path}")
        path.write_text(json.dumps(flags, indent=2, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8")

    def close(self) -> None:
        if not self._closed:
            for f in self._files.values():
                f.close()
            self._transcript.close()
            self._closed = True


def append_manifest(path: str | os.PathLike, record: dict) -> None:
    """Manifest is append-only JSON Lines despite the .json name."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
