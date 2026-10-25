"""model.py — the sole model gateway.

Native Ollama tool calls only.  A text reply that is not a tool call is never
parsed into an action.  Every request and response, including the thinking
trace and usage counters, is appended verbatim to ``raw_calls.jsonl``.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CHAT = OLLAMA_HOST + "/api/chat"
OLLAMA_SHOW = OLLAMA_HOST + "/api/show"


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
                 temperature: float = 0.7, num_ctx: int = 16384,
                 seed: int = 0, transport: Callable[[dict, dict], dict] | None = None,
                 max_retries: int = 5, max_consecutive: int = 6) -> None:
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
        self._consecutive = 0
        self._digest = self._lookup_digest()
        self.raw_path = os.path.join(self.run_dir, "raw_calls.jsonl")

    def _lookup_digest(self) -> str:
        try:
            out = subprocess.check_output(["ollama", "list"], text=True,
                                          stderr=subprocess.DEVNULL, timeout=5)
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == self.model:
                    return parts[1]
        except Exception:
            pass
        return ""

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
            self._consecutive = 0
            rec.update({"response": data, "latency_s": latency, "status": "ok"})
            self._append(rec)
            return resp
        except TransportCollapse as exc:
            rec.update({"status": "infra", "error": str(exc)})
            self._append(rec)
            raise

    def _post(self, payload: dict, meta: dict) -> tuple[dict, float]:
        last: Exception | None = None
        for _ in range(self.max_retries + 1):
            t0 = time.time()
            try:
                if self.transport is not None:
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
                if 400 <= exc.code < 500:
                    # a malformed request is not a transport collapse; report it
                    raise TransportError(f"HTTP {exc.code}: {exc.reason}") from exc
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError,
                    TransportError) as exc:
                last = exc
            self._consecutive += 1
            if self._consecutive >= self.max_consecutive:
                raise TransportCollapse(str(last))
            time.sleep(min(2 ** _, 15))
        raise TransportCollapse(str(last))

    def _append(self, record: dict) -> None:
        with open(self.raw_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
