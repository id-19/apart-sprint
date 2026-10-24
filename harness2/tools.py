"""tools.py — sandboxed file read/write for agents (build-plan §3.5)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ToolResult:
    ok: bool
    content: str = ""
    error: str = ""          # populated when ok is False
    path: str = ""           # the resolved absolute path actually touched


class FileTools:
    """Scoped read/write rooted at one run directory."""

    def __init__(self, run_dir: str, read_whitelist: Optional[List[str]] = None) -> None:
        self.run_dir = os.path.realpath(run_dir)
        os.makedirs(self.run_dir, exist_ok=True)
        self.whitelist = {os.path.realpath(p) for p in (read_whitelist or [])}
        for p in self.whitelist:
            if not os.path.isfile(p):
                raise FileNotFoundError(f"whitelist path does not exist: {p}")

    # ---- resolution -------------------------------------------------------
    def _in_run_dir(self, path: str) -> str:
        """Resolve `path` (possibly relative) to an absolute path inside run_dir."""
        cand = os.path.realpath(os.path.join(self.run_dir, path)) \
            if not os.path.isabs(path) else os.path.realpath(path)
        if not (cand == self.run_dir or cand.startswith(self.run_dir + os.sep)):
            raise PermissionError(f"write escapes run dir: {path!r}")
        return cand

    def _resolve_read(self, path: str) -> str:
        """A read is allowed if the real path is inside run_dir OR on the whitelist."""
        cand = os.path.realpath(os.path.join(self.run_dir, path)) \
            if not os.path.isabs(path) else os.path.realpath(path)
        if cand == self.run_dir or cand.startswith(self.run_dir + os.sep):
            return cand
        if cand in self.whitelist:
            return cand
        raise PermissionError(f"read not allowed: {path!r}")

    # ---- the two tools ----------------------------------------------------
    def write_file(self, path: str, content: str) -> ToolResult:
        try:
            target = self._in_run_dir(path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(ok=True, path=target,
                              content=f"wrote {len(content)} chars")
        except (PermissionError, OSError) as e:
            return ToolResult(ok=False, error=str(e), path=path)

    def read_file(self, path: str) -> ToolResult:
        try:
            target = self._resolve_read(path)
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            return ToolResult(ok=True, path=target, content=data)
        except (PermissionError, OSError) as e:
            return ToolResult(ok=False, error=str(e), path=path)


def describe() -> dict:
    """Schemas handed to the model (what it is told it has)."""
    return {
        "write_file": {"path": "relative or run-local path", "content": "full text"},
        "read_file": {"path": "relative path, run-local, or a whitelisted reference path"},
    }
