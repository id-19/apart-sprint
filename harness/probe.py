"""probe.py — one real call through the real prompt, to size the seed run.

    python3 harness/probe.py [model] [bits]
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine import Engine, make_flow, load_prices
from agents import SYSTEM, chat, parse_reply, route, turn_prompt
import random

root = Path(__file__).resolve().parent.parent
model = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:2b"
bits = int(sys.argv[2]) if len(sys.argv) > 2 else 80

prices = load_prices(root / "data", 10)
eng = Engine(prices, make_flow(6, 10, random.Random(8)), seed=1, n_days=10)
names = ["A1", "A2", "A3", "H1", "H2", "H3"]
obs = eng.observe(0)
obs["_names"] = names
prompt = turn_prompt(obs, "A1", ["A2", "A3"], [], bits, "forum", 10, "")
print(f"model={model} bits={bits} prompt_chars={len(prompt)}")

for attempt in (1, 2):
    t0 = time.time()
    text, secs, raw = chat(model, SYSTEM, prompt, num_predict=96, think=False)
    print(f"attempt {attempt}: {secs:.1f}s eval={raw.get('eval_count')} "
          f"prompt_tok={raw.get('prompt_eval_count')} done={raw.get('done_reason')}")
    print("  raw:", repr(text[:300]))
    parsed, flags = parse_reply(text)
    kept, rf = route(parsed["message"], bits)
    print("  parsed:", {k: (v[:60] if isinstance(v, str) else v) for k, v in parsed.items()},
          "flags:", flags + rf, "kept_bytes:", len(kept.encode()))
    print("  validated orders:", eng.validate(0, parsed["orders"])[0])
