"""ollama_client.py — the SOLE model gateway (R1, R5, R6, R9).

No other module may call Ollama. Every call:
  * passes options.seed, think:false, no JSON mode, stream:false;
  * is appended verbatim to raw_calls.jsonl (flushed per line);
  * is memory-sampled (our RSS + ollama-runner RSS + free pages) into memory.jsonl;
  * distinguishes transport failure from model behaviour: after `max_consecutive`
    consecutive transport errors the caller sees TransportCollapse, which the engine
    converts to an INFRA verdict and stage abort — never a "malformed" run.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/chat"


class TransportCollapse(Exception):
    """Raised by chat() when the transport has died; the stage must abort."""


@dataclass
class CallRecord:
    cell: str
    seat: str
    round: int
    model: str
    seed: int
    system: str
    user: str
    response: str = ""
    status: str = "ok"           # ok | infra
    error: str = ""
    latency_s: float = 0.0

    def to_json(self) -> str:
        return json.dumps(self.__dict__)


@dataclass
class OllamaClient:
    """One gateway instance per run. Binds itself to a run directory's logs."""

    run_dir: str
    cell: str
    model: str
    seed: int = 0
    temperature: float = 0.7
    num_ctx: int = 4096
    keep_alive: str = "10m"
    max_retries: int = 2
    max_consecutive: int = 3
    # test hook: replace the transport with a scripted function
    transport: Optional[Callable[[dict], dict]] = None
    _consecutive_failures: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        os.makedirs(self.run_dir, exist_ok=True)
        self.raw_path = os.path.join(self.run_dir, "raw_calls.jsonl")
        self.mem_path = os.path.join(self.run_dir, "memory.jsonl")

    # ---- the only public entry -------------------------------------------
    def chat(self, system: str, user: str, seat: str, round: int) -> CallRecord:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "seed": self.seed,
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
            "keep_alive": self.keep_alive,
        }
        rec = CallRecord(cell=self.cell, seat=seat, round=round,
                         model=self.model, seed=self.seed, system=system, user=user)
        try:
            data = self._post(payload)
            rec.response = (data.get("message") or {}).get("content", "")
            self._consecutive_failures = 0
        except TransportCollapse:
            rec.status = "infra"
            rec.error = "transport collapsed"
            self._append(self.raw_path, rec.to_json())
            raise
        rec.latency_s = getattr(self, "_last_latency", 0.0)
        self._append(self.raw_path, rec.to_json())
        self._sample_memory()
        return rec

    # ---- transport --------------------------------------------------------
    def _post(self, payload: dict) -> dict:
        import time
        last_err: Optional[Exception] = None
        for _ in range(self.max_retries + 1):
            try:
                t0 = time.time()
                if self.transport is not None:
                    data = self.transport(payload)
                else:
                    req = urllib.request.Request(
                        OLLAMA_URL, data=json.dumps(payload).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=600) as r:
                        data = json.loads(r.read().decode())
                self._last_latency = time.time() - t0
                return data
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                last_err = e
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.max_consecutive:
                    raise TransportCollapse(str(e)) from e
        raise TransportCollapse(str(last_err))

    # ---- logging / memory --------------------------------------------------
    def _append(self, path: str, line: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    def _sample_memory(self) -> None:
        try:
            our_rss = int(subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())]).decode().strip() or 0) * 1024
            runner_rss = 0
            for line in subprocess.check_output(
                    ["ps", "-axo", "rss=,command="]).decode().splitlines():
                if "ollama runner" in line:
                    runner_rss = max(runner_rss, int(line.split()[0]) * 1024)
            vm = subprocess.check_output(["vm_stat"]).decode()
            free_pages = int(next(l.split()[-1].rstrip(".")
                                  for l in vm.splitlines() if l.startswith("Pages free")))
            rec = {"our_rss_mb": our_rss / 1e6, "ollama_runner_rss_mb": runner_rss / 1e6,
                   "free_mb": free_pages * 16384 / 1e6}
        except Exception as e:  # memory sampling must never crash a run
            rec = {"error": str(e)}
        self._append(self.mem_path, json.dumps(rec))
