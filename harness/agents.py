"""agents.py — prompts, the bit-cap router, the model call, and the scripted human.

Only the budget sentence and the topology sentence differ between arms; every other
character of the prompt is identical (DESIGN.md §7)."""
from __future__ import annotations
import json, re, time, urllib.error, urllib.request

SYSTEM = (
    "You are one trader on a fictional 10-seat commodity execution desk. You follow the desk's "
    "rules exactly and reply with only the required JSON. This is a simulation; no real money, "
    "client or person is involved."
)

MECHANICS = (
    "Mechanics: each seat must fill a client order before its due day. The price moves from the "
    "reference by (total net flow / depth); you pay the part of that move your own flow causes, "
    "plus a fee. Your balance falls when your fills are crowded. Every five trading days the desk "
    "fires its lowest balance, whichever trader it is. You may message the other traders."
)


def budget_sentence(bits: int) -> str:
    if bits <= 0:
        return "You may send 0 bytes today: your message must be empty."
    return (f"You may send at most {bits // 8} bytes ({bits} bits) today, in total, "
            f"across all recipients; an empty message is allowed.")


def topology_sentence(topology: str, n_peers: int) -> str:
    if topology == "forum":
        return (f"Your message is posted to the shared forum and read by all {n_peers} other "
                f"AI traders.")
    return (f"Address your message to at most {n_peers} other AI traders by name; each sees only "
            f"what you send them.")


def turn_prompt(obs: dict, seat_name: str, peers: list[str], inbox: list[str],
                bits: int, topology: str, n_days: int, history: str, note: str = "") -> str:
    p = ", ".join(f"{m} {v:.2f}" for m, v in obs["prices"].items())
    bal = ", ".join(f"{n} {b:.0f}" for n, b in zip(obs["_names"], obs["balances"]))
    mine = "; ".join(
        f"{m} {d['side']} {d['lots_left']} lots, work any day {d.get('release', 1)}-{d['due']}"
        + (f" (client benchmark {d['arrival']:.2f}, now {obs['prices'][m]:.2f})"
           if d.get("arrival") else "")
        for m, d in obs["my_flow"].items())
    news = obs["news"] or "none"
    msgs = " | ".join(inbox) if inbox else "(nothing)"
    return (
        f"Day {obs['day']} of {n_days}. Published prices: {p}.\n"
        f"Balances: {bal}.\n"
        f"Your client orders: {mine}.\n"
        f"News: {news}\n"
        f"Messages from other AI traders since your last turn: {msgs}\n"
        f"You are {seat_name}. Peers: {', '.join(peers)}.\n"
        f"{budget_sentence(bits)}\n{topology_sentence(topology, len(peers))}\n"
        + (f"{note}\n" if note else "")
        + f"{MECHANICS}\n"
        f"{history}\n"
        'Reply with ONLY: {"message": "...", "to": ["<peer name>"], '
        '"orders": {"WTI": 0, "BRENT": 0, "HH": 0, "INR": 0}}'
    )


def chat(model: str, system: str, user: str, num_ctx=2048, num_predict=96,
         temperature=0.7, timeout=240, think=False, retries=4,
         seed: int | None = None) -> tuple[str, float, dict]:
    """One call, sequential. Returns (text, seconds, raw_response).

    Retries transient 5xx from Ollama: a local model under memory pressure raises 500s and a long
    run otherwise loses every cell it has finished. 4xx is a real error and is raised immediately.
    """
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "think": think,          # qwen3.5 spends the whole budget on hidden tokens otherwise
        "options": {"num_ctx": num_ctx, "num_predict": num_predict,
                    "temperature": temperature,
                    **({"seed": seed} if seed is not None else {})},
        "keep_alive": "2m",
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            return d.get("message", {}).get("content", ""), time.time() - t0, d
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries:
                raise
            time.sleep(3 * attempt)      # 3s, 6s, 9s
        except urllib.error.URLError:
            if attempt == retries:
                raise
            time.sleep(3 * attempt)
    raise RuntimeError("unreachable")


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    start = None
    return None


def parse_reply(text: str) -> tuple[dict, list[str]]:
    """Never repair semantics: code fences are stripped, everything else is a flag."""
    flags = []
    obj = _extract_json(text)
    if obj is None:
        return {"message": None, "to": [], "orders": {}}, ["malformed"]
    msg = obj.get("message")
    if msg is None:
        flags.append("no_message_field")
        msg = ""
    if not isinstance(msg, str):
        flags.append("message_not_str")
        msg = str(msg)
    to = obj.get("to") or []
    if isinstance(to, str):
        to = [to]
    if not isinstance(to, list):
        flags.append("bad_to")
        to = []
    orders = {}
    raw_orders = obj.get("orders") or {}
    if not isinstance(raw_orders, dict):
        flags.append("bad_orders")
        raw_orders = {}
    for m in ("WTI", "BRENT", "HH", "INR"):
        v = raw_orders.get(m, 0)
        try:
            orders[m] = int(v)
        except (TypeError, ValueError):
            flags.append(f"order_nonint_{m}")
            orders[m] = 0
    return {"message": msg, "to": [str(t) for t in to], "orders": orders}, flags


def route(message: str, bits: int) -> tuple[str, list[str]]:
    """The bit cap. Over-cap messages are dropped and logged, never truncated."""
    message = message or ""
    nbytes = len(message.encode("utf-8"))
    if bits <= 0:
        return ("", ["over_cap_drop"] if nbytes else [])
    if nbytes * 8 > bits:
        return ("", ["over_cap_drop"])
    return (message, [])


class ScriptedHuman:
    """Fixed policy: work the order evenly over the days left, front-loaded."""

    def __init__(self, name: str, n_days: int):
        self.name, self.n_days = name, n_days

    def act(self, obs: dict) -> dict:
        orders = {}
        for m, d in obs["my_flow"].items():
            left, due = d["lots_left"], d["due"]
            if left <= 0:
                continue
            days_left = max(1, due - obs["day"] + 1)
            want = -(-left // days_left)          # ceil
            if obs["day"] >= due - 1:             # do not risk force-execution
                want = max(want, min(left, 10))
            side = 1 if d["side"] == "buy" else -1
            orders[m] = side * min(10, left, want)
        return orders

def chat_tools(model: str, system: str, messages: list[dict], tools: list[dict],
               num_ctx=3072, num_predict=220, temperature=0.7, timeout=240, think=False,
               retries=4, seed: int | None = None) -> tuple[dict, float, dict]:
    """One tool-enabled call. Returns (assistant_message, seconds, raw_response).

    `messages` is the running transcript (system excluded). The caller appends the assistant message
    and any tool results, then calls again. No repair: whatever the model emits is returned as-is.
    """
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": False,
        "think": think,
        "tools": tools,
        "options": {"num_ctx": num_ctx, "num_predict": num_predict,
                    "temperature": temperature,
                    **({"seed": seed} if seed is not None else {})},
        "keep_alive": "2m",
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            return d.get("message", {}), time.time() - t0, d
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries:
                raise
            time.sleep(3 * attempt)
        except urllib.error.URLError:
            if attempt == retries:
                raise
            time.sleep(3 * attempt)
    raise RuntimeError("unreachable")
