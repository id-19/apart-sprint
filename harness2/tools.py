"""tools.py — the seat's in-world tool surface.

Every tool result is an in-world sentence or document excerpt.  There is no
unmeasured channel: file writes are private to the seat, reference files are
read-only, and the common room is the only shared write (charged by the comms
ledger).  ``search_web`` is a local, canned index over the scenario's HTML
reference folder; it never touches the network.
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class ToolResult:
    ok: bool
    content: str
    meta: dict = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., ToolResult]
    terminal: bool = False
    finish: bool = False
    kind: str = "read"  # read | file | comm | action | finish

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------------------------------------------------------------------------
# local HTML corpus
# ---------------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "were", "be", "been", "at", "by", "from", "as", "that", "this",
    "it", "its", "their", "they", "we", "our", "you", "your", "what", "which",
    "who", "how", "why", "when", "where", "about", "into", "over", "after",
}


def _plain(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        raw = _TAG.sub(" ", raw)
        raw = html.unescape(raw)
    return _WS.sub(" ", raw).strip()


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP}


class Corpus:
    """Read-only reference documents for one scenario."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._docs: dict[str, dict] | None = None

    def _load(self) -> dict[str, dict]:
        if self._docs is not None:
            return self._docs
        docs: dict[str, dict] = {}
        if self.root.is_dir():
            for path in sorted(self.root.rglob("*")):
                if path.suffix.lower() not in (".html", ".htm", ".txt", ".md"):
                    continue
                rel = path.relative_to(self.root).as_posix()
                body = _plain(path)
                title = path.stem.replace("_", " ").replace("-", " ").title()
                m = re.search(r"(?is)<title[^>]*>(.*?)</title>", path.read_text(
                    encoding="utf-8", errors="replace"))
                if m:
                    title = html.unescape(_TAG.sub("", m.group(1))).strip()
                docs[rel] = {"path": rel, "title": title, "body": body,
                             "tokens": _tokens(title + " " + body)}
        self._docs = docs
        return docs

    def list(self) -> list[dict]:
        return [{"path": d["path"], "title": d["title"]} for d in self._load().values()]

    def read(self, rel: str) -> str:
        rel = rel.removeprefix("reference/").lstrip("/")
        if rel not in self._load():
            raise FileNotFoundError(rel)
        return self._load()[rel]["body"]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        q = _tokens(query)
        scored = []
        for doc in self._load().values():
            overlap = len(q & doc["tokens"])
            if overlap == 0:
                continue
            # title hits count more; long documents do not win by length alone
            title_hits = len(q & _tokens(doc["title"]))
            score = overlap + 2 * title_hits
            snippet = _snippet(doc["body"], q)
            scored.append((score, doc["title"], doc["path"], snippet))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [{"title": t, "path": p, "snippet": s} for _, t, p, s in scored[:limit]]


def _snippet(body: str, terms: set[str], width: int = 220) -> str:
    low = body.lower()
    pos = -1
    for term in terms:
        pos = low.find(term)
        if pos >= 0:
            break
    if pos < 0:
        return body[:width].strip()
    start = max(0, pos - 70)
    end = min(len(body), start + width)
    return ("..." if start else "") + body[start:end].strip() + (
        "..." if end < len(body) else "")


# ---------------------------------------------------------------------------
# per-seat toolbox
# ---------------------------------------------------------------------------

def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required or list(props), "additionalProperties": False}


class Toolbox:
    """All tools one seat can call during one cycle.

    ``run_dir/private/<seat>`` is the seat's persistent workspace.  Reference
    documents live outside it and are read-only.  The ledger, when present,
    owns message admission and delivery.
    """

    def __init__(self, *, run_dir: str | Path, seat: str, corpus: Corpus | None,
                 ledger=None, extra_tools: Iterable[ToolSpec] = ()) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.seat = seat
        self.corpus = corpus
        self.ledger = ledger
        self.extra_tools = list(extra_tools)
        self.private = self.run_dir / "private" / seat
        self.private.mkdir(parents=True, exist_ok=True)

    # -- path handling -----------------------------------------------------
    def _private(self, rel: str) -> Path:
        rel = (rel or "").strip().lstrip("/")
        cand = (self.private / rel).resolve()
        if cand != self.private and self.private not in cand.parents:
            raise PermissionError("that path is outside your desk folder")
        return cand

    # -- basic tools -------------------------------------------------------
    def list_files(self) -> ToolResult:
        files = sorted(p.relative_to(self.private).as_posix()
                       for p in self.private.rglob("*") if p.is_file())
        if not files:
            return ToolResult(True, "Your desk folder is empty.")
        return ToolResult(True, "Files in your desk folder:\n" + "\n".join(f"- {f}" for f in files))

    def read_file(self, path: str) -> ToolResult:
        path = str(path or "").strip()
        try:
            if path.startswith("reference/") or (self.corpus and self._corpus_has(path)):
                if self.corpus is None:
                    return ToolResult(False, "No reference documents are available here.")
                return ToolResult(True, self.corpus.read(path))
            target = self._private(path)
            if not target.is_file():
                return ToolResult(False, f"No file named {path!r} in your desk folder.")
            return ToolResult(True, target.read_text(encoding="utf-8", errors="replace"))
        except (OSError, PermissionError, FileNotFoundError) as exc:
            return ToolResult(False, f"Could not read {path!r}: {exc}")

    def _corpus_has(self, rel: str) -> bool:
        try:
            return rel in {d["path"] for d in self.corpus.list()}
        except Exception:
            return False

    def write_file(self, path: str, content: str) -> ToolResult:
        path = str(path or "").strip()
        if not path:
            return ToolResult(False, "A file name is required.")
        if path.startswith("reference/"):
            return ToolResult(False, "Reference documents are read-only.")
        try:
            target = self._private(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            return ToolResult(True, f"Saved {path} ({len(str(content))} characters).")
        except (OSError, PermissionError) as exc:
            return ToolResult(False, f"Could not save {path!r}: {exc}")

    def search_web(self, query: str) -> ToolResult:
        if self.corpus is None:
            return ToolResult(False, "No reference index is available here.")
        hits = self.corpus.search(str(query or ""))
        if not hits:
            return ToolResult(True, f"No notices or reports matched {query!r}.")
        lines = [f"{i}. {h['title']} — {h['snippet']}\n   reference/{h['path']}"
                 for i, h in enumerate(hits, 1)]
        return ToolResult(True, "Search results:\n" + "\n".join(lines))

    # -- comms -------------------------------------------------------------
    def post_to_common_room(self, text: str) -> ToolResult:
        if self.ledger is None:
            return ToolResult(False, "There is no common room here.")
        if not str(text or "").strip():
            return ToolResult(False, "A message needs some text.")
        r = self.ledger.post(self.seat, str(text))
        return ToolResult(r.ok, r.render(), {"kind": "comm", "message": r.message,
                                             "reason": r.reason, "cost": r.cost,
                                             "remaining": r.remaining})

    def send_direct_message(self, to, text: str) -> ToolResult:
        if self.ledger is None:
            return ToolResult(False, "There is no direct line here.")
        if isinstance(to, str):
            to = [to]
        recipients = list(to or [])
        if not recipients:
            return ToolResult(False, "No recipient desk was named.")
        if not str(text or "").strip():
            return ToolResult(False, "A message needs some text.")
        r = self.ledger.dm(self.seat, recipients, str(text))
        return ToolResult(r.ok, r.render(), {"kind": "comm", "message": r.message,
                                             "reason": r.reason, "cost": r.cost,
                                             "remaining": r.remaining})

    # -- registry ----------------------------------------------------------
    def tools(self) -> list[ToolSpec]:
        out = [
            ToolSpec("list_files", "List the files in your private desk folder.",
                     _schema({}), lambda **_: self.list_files(), kind="file"),
            ToolSpec("read_file", "Read a file from your desk folder or a reference document "
                     "returned by search_web.",
                     _schema({"path": {"type": "string",
                                       "description": "e.g. notes.txt or reference/notice.html"}}),
                     lambda path, **_: self.read_file(path), kind="file"),
            ToolSpec("write_file", "Save a note in your private desk folder. It persists "
                     "across exchanges and cycles and no other desk can see it.",
                     _schema({"path": {"type": "string"},
                              "content": {"type": "string"}}),
                     lambda path, content, **_: self.write_file(path, content), kind="file"),
            ToolSpec("search_web", "Search the local index of public notices, bulletins, "
                     "and reports. Returns titles, excerpts, and reference paths.",
                     _schema({"query": {"type": "string"}}),
                     lambda query, **_: self.search_web(query), kind="read"),
        ]
        if self.ledger is not None and self.ledger.enabled:
            out += [
                ToolSpec("post_to_common_room",
                         "Post a message to the common room. Everyone else can read it.",
                         _schema({"text": {"type": "string"}}),
                         lambda text, **_: self.post_to_common_room(text), kind="comm"),
                ToolSpec("send_direct_message",
                         "Send a direct message to one or more desks.",
                         _schema({"to": {"type": "array", "items": {"type": "string"},
                                         "minItems": 1,
                                         "description": "desk labels, e.g. [\"B\"]"},
                                  "text": {"type": "string"}}),
                         lambda to, text, **_: self.send_direct_message(to, text),
                         kind="comm"),
            ]
        out.extend(self.extra_tools)
        return out

    def call(self, name: str, arguments: dict) -> ToolResult:
        for tool in self.tools():
            if tool.name == name:
                try:
                    return tool.handler(**dict(arguments or {}))
                except TypeError as exc:
                    return ToolResult(False, f"{name}: {exc}")
        return ToolResult(False, f"No tool named {name!r} is available now.")
