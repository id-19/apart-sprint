"""model.py — the sole model gateway.

Native Ollama tool calls only.  A text reply that is not a tool call is never
parsed into an action.  Every request and response, including the thinking
trace and usage counters, is appended verbatim to ``raw_calls.jsonl``.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

# Concurrent cells each build their own client; the digest lookup shells out to
# `ollama list`, so it is done once per model per process rather than once per
# cell.  The transport itself has no shared state.
_DIGEST_LOCK = threading.Lock()
_DIGEST_CACHE: dict[str, str] = {}

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CHAT = OLLAMA_HOST + "/api/chat"
OLLAMA_SHOW = OLLAMA_HOST + "/api/show"


def concurrent_map(fn: Callable, items, max_workers: int | None = None) -> list:
    """Call ``fn`` on independent items at the same time, results in order.

    One exchange is already semantically simultaneous: no seat sees another
    seat's message until the exchange closes, and each seat spends only its own
    allowance.  Calling the model seat by seat therefore lengthens the clock
    without changing what any seat can know, so the calls go out together.
    A failure is re-raised only after every call has been waited for; leaving
    an executor on its first exception would abandon calls already in flight
    and lose their raw records.
    """
    items = list(items)
    workers = min(len(items), max_workers or len(items))
    if workers <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, item) for item in items]
        results: list = [None] * len(futures)
        error: BaseException | None = None
        for i, fut in enumerate(futures):
            try:
                results[i] = fut.result()
            except BaseException as exc:  # re-raised below, after the drain
                if error is None:
                    error = exc
        if error is not None:
            raise error
        return results


class TransportError(Exception):
    pass


class TransportCollapse(Exception):
    pass


@dataclass
class ModelResponse:
    content: str = ""
    thinking: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""
    digest: str = ""
    latency_s: float = 0.0
    raw: dict = field(default_factory=dict)
    status: str = "ok"
    error: str = ""


def _norm_tool_calls(message: dict) -> list[dict]:
    out = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        name = fn.get("name") or call.get("name") or ""
        args = fn.get("arguments", call.get("arguments", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"value": args}
        out.append({"function": {"name": name, "arguments": args}})
    return out


class ModelClient:
    def __init__(self, *, run_dir: str | os.PathLike, cell_id: str, model: str,
                 provider: str = "ollama", think: bool | None = True,
                 temperature: float = 1.0, num_ctx: int = 16384,
                 seed: int = 0, transport: Callable[[dict, dict], dict] | None = None,
                 max_retries: int = 5, max_consecutive: int = 10) -> None:
        self.run_dir = os.fspath(run_dir)
        os.makedirs(self.run_dir, exist_ok=True)
        self.cell_id = cell_id
        self.model = model
        self.provider = provider
        self.think = think
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.seed = seed
        self.transport = transport
        self.max_retries = max_retries
        self.max_consecutive = max_consecutive
        # Seats share one client and now call it at the same time: the retry
        # counter and the raw transcript each need a lock, or two turns can
        # interleave their lines and a collapse can be counted twice.
        self._lock = threading.Lock()
        self._consecutive = 0
        # (a 429 burst is counted inside the call that meets it, not here)
        self._digest = self._lookup_digest()
        self.raw_path = os.path.join(self.run_dir, "raw_calls.jsonl")

    def _lookup_digest(self) -> str:
        with _DIGEST_LOCK:
            if self.model in _DIGEST_CACHE:
                return _DIGEST_CACHE[self.model]
        digest = ""
        try:
            out = subprocess.check_output(["ollama", "list"], text=True,
                                          stderr=subprocess.DEVNULL, timeout=5)
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == self.model:
                    digest = parts[1]
                    break
        except Exception:
            pass
        with _DIGEST_LOCK:
            _DIGEST_CACHE[self.model] = digest
        return digest

    def chat(self, *, messages: list[dict], tools: list[dict] | None = None,
             seat: str = "", cycle: int = 0, exchange: int = 0,
             num_predict: int = 512) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "seed": self.seed,
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": num_predict,
            },
            "keep_alive": "10m",
        }
        if self.think is not None:
            payload["think"] = self.think
        if tools:
            payload["tools"] = tools
        meta = {"seat": seat, "cycle": cycle, "exchange": exchange}
        rec = {"cell_id": self.cell_id, "seat": seat, "cycle": cycle,
               "exchange": exchange, "model": self.model,
               "model_digest": self._digest, "ts": time.time(),
               "request": payload}
        try:
            data, latency = self._post(payload, meta)
            msg = data.get("message") or {}
            resp = ModelResponse(
                content=msg.get("content") or "",
                thinking=msg.get("thinking") or "",
                tool_calls=_norm_tool_calls(msg),
                usage=data.get("usage") or {},
                model=data.get("model") or self.model,
                digest=self._digest,
                latency_s=latency,
                raw=data,
            )
            self._reset_streak()
            rec.update({"response": data, "latency_s": latency, "status": "ok"})
            self._append(rec)
            return resp
        except TransportCollapse as exc:
            rec.update({"status": "infra", "error": str(exc)})
            self._append(rec)
            raise
        except TransportError as exc:
            # A 4xx is a bad request, not a collapse; it is still worth a
            # record, or the failed call vanishes from the run tree.
            rec.update({"status": "error", "error": str(exc)})
            self._append(rec)
            raise

    def _post(self, payload: dict, meta: dict) -> tuple[dict, float]:
        last: Exception | None = None
        attempt = 0
        throttled = 0
        while attempt <= self.max_retries:
            t0 = time.time()
            wait = min(2 ** attempt, 15)
            try:
                if self.transport is not None:
                    wait = 0.0
                    data = self.transport(payload, meta)
                else:
                    req = urllib.request.Request(
                        OLLAMA_CHAT, data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=900) as r:
                        data = json.loads(r.read().decode("utf-8"))
                if not isinstance(data, dict):
                    raise TransportError("response was not a JSON object")
                return data, time.time() - t0
            except urllib.error.HTTPError as exc:
                last = exc
                if 400 <= exc.code < 500 and exc.code not in (408, 429):
                    # a malformed request is not a transport collapse; report it
                    raise TransportError(f"HTTP {exc.code}: {exc.reason}") from exc
                if exc.code == 429:
                    # The endpoint is asking us to wait.  That is expected when
                    # several cells run at once, and it must never by itself end
                    # a cell: it has its own patient budget (a long sleep per
                    # refusal, up to ~15 minutes in total) and it does not feed
                    # the collapse streak, so a busy hour is slow, not fatal.
                    throttled += 1
                    if throttled > 30:
                        raise TransportCollapse(f"rate limited for {throttled} "
                                                f"attempts: {exc}")
                    time.sleep(min(5.0 * throttled, 45.0))
                    continue
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError,
                    TransportError) as exc:
                last = exc
            attempt += 1
            self._bump_streak()
            if self._streak() >= self.max_consecutive:
                raise TransportCollapse(str(last))
            time.sleep(wait)
        raise TransportCollapse(str(last))

    def _reset_streak(self) -> None:
        with self._lock:
            self._consecutive = 0

    def _bump_streak(self) -> None:
        with self._lock:
            self._consecutive += 1

    def _streak(self) -> int:
        with self._lock:
            return self._consecutive

    def _append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            with open(self.raw_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
