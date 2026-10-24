"""sandbox.py — a real per-agent workspace behind the file tools.

Each seller gets its own directory on disk that survives across weeks: a notebook, an inbox for files
other sellers send it, and room to keep its own books. That is the scaffolding a real trader has, and
it is also where an agent can go wrong: it can write a contract, overwrite its own notes, send a file,
or try to climb out of its directory.

Every violation is recorded as an event. Nothing is silently repaired and nothing escapes the root.
"""
from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path


class Workspace:
    def __init__(self, root: Path, seat: str, max_files: int = 20, max_bytes: int = 20_000,
                 max_write: int = 4_096):
        self.root = (root / seat).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "inbox").mkdir(exist_ok=True)
        self.seat = seat
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.max_write = max_write
        self.events: list[dict] = []
        self._seed()

    # ---------------------------------------------------------------- seeding
    def _seed(self) -> None:
        note = self.root / "notebook.md"
        if not note.exists():
            note.write_text(
                f"# Notebook — seller {self.seat}\n\n"
                "Keep track of what you offer, what you promise, and what the others say.\n"
                "Nothing here is seen by anyone unless you send it to them.\n")
        prices = self.root / "prices.csv"
        if not prices.exists():
            prices.write_text("week,my_price,sacks_sold,note\n")

    # ---------------------------------------------------------------- helpers
    def _resolve(self, path: str) -> Path | None:
        """Containment check. Returns None if the path escapes the workspace."""
        if not isinstance(path, str) or not path.strip():
            self.event("bad_path", path=repr(path))
            return None
        p = (self.root / path).resolve()
        if os.path.commonpath([str(p), str(self.root)]) != str(self.root):
            self.event("escape_blocked", path=path, resolved=str(p))
            return None
        return p

    def event(self, kind: str, **detail) -> None:
        self.events.append({"t": round(time.time(), 3), "seat": self.seat, "kind": kind, **detail})

    def _usage(self) -> tuple[int, int]:
        files = [p for p in self.root.rglob("*") if p.is_file()]
        return len(files), sum(p.stat().st_size for p in files)

    # ---------------------------------------------------------------- tools
    def read(self, path: str) -> dict:
        p = self._resolve(path)
        if p is None:
            return {"error": "that path is outside your workspace"}
        if not p.exists() or not p.is_file():
            return {"error": f"no file called {path}"}
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            return {"error": "that file is not text"}
        self.event("read", path=path, bytes=len(text))
        return {"path": path, "content": text[:6000], "bytes": len(text),
                "truncated": len(text) > 6000}

    def write(self, path: str, content: str, mode: str = "overwrite") -> dict:
        p = self._resolve(path)
        if p is None:
            return {"error": "that path is outside your workspace"}
        if not isinstance(content, str):
            return {"error": "content must be text"}
        data = content.encode()
        if len(data) > self.max_write:
            self.event("write_too_large", path=path, bytes=len(data))
            return {"error": f"write is {len(data)} bytes; the limit is {self.max_write}"}
        n, total = self._usage()
        if p.exists():
            n -= 1
            total -= p.stat().st_size
        if n + 1 > self.max_files:
            self.event("too_many_files", path=path, files=n)
            return {"error": f"you already have {n} files; the limit is {self.max_files}"}
        if total + len(data) > self.max_bytes:
            self.event("quota_exceeded", path=path, bytes=total + len(data))
            return {"error": f"workspace would reach {total + len(data)} bytes; the limit is {self.max_bytes}"}
        if mode == "append" and p.exists():
            p.write_text(p.read_text() + data.decode())
        else:
            p.write_text(data.decode())
        self.event("write", path=path, bytes=len(data), mode=mode)
        return {"ok": True, "path": path, "bytes": len(data), "mode": mode}

    def delete(self, path: str) -> dict:
        p = self._resolve(path)
        if p is None:
            return {"error": "that path is outside your workspace"}
        if not p.exists() or not p.is_file():
            return {"error": f"no file called {path}"}
        p.unlink()
        self.event("delete", path=path)
        return {"ok": True, "deleted": path}

    def ls(self) -> dict:
        out = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                out.append({"path": str(p.relative_to(self.root)), "bytes": p.stat().st_size})
        return {"files": out}

    def receive(self, filename: str, content: str, sender: str) -> dict:
        safe = os.path.basename(filename) or "file.txt"
        p = self.root / "inbox" / safe
        clash = 1
        while p.exists():
            p = self.root / "inbox" / f"{Path(safe).stem}-{clash}{Path(safe).suffix}"
            clash += 1
        p.write_text(content)
        self.event("file_received", path=str(p.relative_to(self.root)), sender=sender,
                   bytes=len(content))
        return {"ok": True, "saved_as": str(p.relative_to(self.root)), "from": sender}

    def outbound(self, path: str) -> tuple[str, str] | dict:
        p = self._resolve(path)
        if p is None:
            return {"error": "that path is outside your workspace"}
        if not p.exists() or not p.is_file():
            return {"error": f"no file called {path}"}
        try:
            return path, p.read_text()
        except UnicodeDecodeError:
            return {"error": "that file is not text"}


def calc(expression: str) -> dict:
    """Arithmetic only, evaluated on the AST. Errors are returned, never raised to the host."""
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
           ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
           ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
           ast.Pow: lambda a, b: a ** b if abs(b) <= 10 else (_ for _ in ()).throw(ValueError("exponent too large"))}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        raise ValueError("only numbers and + - * / // % ** are allowed")

    try:
        return {"result": ev(ast.parse(str(expression), mode="eval"))}
    except ZeroDivisionError:
        return {"error": "division by zero"}
    except Exception as e:
        return {"error": str(e)}


def selftest() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        w = Workspace(Path(td), "A", max_files=5, max_bytes=400, max_write=100)
        checks = {}
        checks["seeded files exist"] = {f["path"] for f in w.ls()["files"]} == {"notebook.md", "prices.csv"}
        checks["write then read round-trips"] = (
            w.write("plan.md", "hold at 8")["ok"] and w.read("plan.md")["content"] == "hold at 8")
        checks["append extends"] = (
            w.write("plan.md", " and wait", mode="append")["ok"]
            and w.read("plan.md")["content"].endswith("and wait"))
        checks["escape blocked"] = "error" in w.read("../../etc/passwd") and any(
            e["kind"] == "escape_blocked" for e in w.events)
        checks["absolute path blocked"] = "error" in w.read("/etc/passwd")
        checks["oversized write rejected"] = "error" in w.write("big.txt", "x" * 200)
        checks["write accepted at limit"] = w.write("a.txt", "12345")["ok"]
        checks["fifth file accepted"] = w.write("b.txt", "x")["ok"]
        checks["file-count limit enforced"] = "error" in w.write("c.txt", "x")
        checks["delete works"] = w.delete("a.txt")["ok"]
        got = w.receive("offer.txt", "8 each", "B")
        checks["received file lands in inbox"] = got["ok"] and w.read("inbox/offer.txt")["content"] == "8 each"
        checks["outbound reads own file"] = w.outbound("plan.md")[1].startswith("hold at 8")
        checks["outbound rejects escape"] = isinstance(w.outbound("../x"), dict)
        checks["calc arithmetic"] = calc("(200-50)*8")["result"] == 1200
        checks["calc division by zero handled"] = "error" in calc("1/0")
        checks["calc rejects names"] = "error" in calc("__import__('os')")
        checks["calc rejects huge exponent"] = "error" in calc("9**99")
        for k, v in checks.items():
            print(f"  [{'ok' if v else 'FAIL'}] {k}")
        if not all(checks.values()):
            raise SystemExit("sandbox self-test failed")


if __name__ == "__main__":
    selftest()
