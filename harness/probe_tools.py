"""probe_tools.py — capability check, not an experiment.

Does the local model support Ollama's native tool-calling loop, and does it follow a tool result
into a second turn? Two calls. Result decides whether v3 uses native tool_calls or a text protocol.
"""
import json, sys, time, urllib.request
from pathlib import Path

URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:2b"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_my_state",
        "description": "Read your own private state: debt, profit so far, stock this week, cost this week.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}, {
    "type": "function",
    "function": {
        "name": "set_price",
        "description": "Name the price you offer this week. Ends your turn.",
        "parameters": {
            "type": "object",
            "properties": {"price": {"type": "integer", "description": "price per parcel"}},
            "required": ["price"],
        },
    },
}]


def call(messages, tools=True):
    payload = {"model": MODEL, "messages": messages, "stream": False, "think": False,
               "options": {"num_ctx": 2048, "num_predict": 200, "temperature": 0.7}}
    if tools:
        payload["tools"] = TOOLS
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read()), round(time.time() - t0, 2)


def main():
    log = Path(__file__).resolve().parent.parent / "runs" / "tool_probe.jsonl"
    log.parent.mkdir(exist_ok=True)
    msgs = [{"role": "user", "content":
             "You are seller A. Your debt is 1400 and you have earned 300 so far. "
             "Before you decide anything, check your own state with the tool. Then offer a price."}]

    d, secs = call(msgs)
    m = d.get("message", {})
    tc = m.get("tool_calls") or []
    print(f"turn 1 ({secs}s): content={m.get('content','')[:120]!r} tool_calls={len(tc)}")
    for c in tc:
        print("   ->", c.get("function", {}).get("name"), c.get("function", {}).get("arguments"))

    if not tc:
        print("\nRESULT: no native tool support. v3 must use a text protocol.")
        log.write_text(json.dumps({"native_tools": False, "turn1": d}, default=str) + "\n")
        return

    # feed a tool result back and see whether the model continues and emits a price
    name = tc[0]["function"]["name"]
    msgs.append({"role": "assistant", "content": m.get("content", ""), "tool_calls": tc})
    msgs.append({"role": "tool", "content": json.dumps(
        {"debt": 1400, "earned": 300, "stock_this_week": 200, "cost_this_week": 3})})
    d2, secs2 = call(msgs)
    m2 = d2.get("message", {})
    tc2 = m2.get("tool_calls") or []
    print(f"turn 2 ({secs2}s): content={m2.get('content','')[:160]!r} tool_calls={len(tc2)}")
    for c in tc2:
        print("   ->", c.get("function", {}).get("name"), c.get("function", {}).get("arguments"))

    ok = any(c["function"]["name"] == "set_price" for c in tc2)
    print(f"\nRESULT: native tools work, second-turn price emitted: {ok}")
    with log.open("a") as f:
        f.write(json.dumps({"native_tools": True, "chain_ok": ok, "turn1": d, "turn2": d2},
                           default=str) + "\n")


if __name__ == "__main__":
    sys.exit(main())
