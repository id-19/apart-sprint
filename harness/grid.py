"""grid.py — run the lab grid sequentially, appending each cell's summary to RESULTS.jsonl as it lands."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab import run_cell

CELLS = [
    {"bits": 800, "topology": "mesh", "seed": 1},
    {"bits": 800, "topology": "forum", "seed": 1},
    {"bits": 80, "topology": "mesh", "seed": 1},
    {"bits": 80, "topology": "forum", "seed": 1},
    {"bits": None, "topology": "mesh", "seed": 1},
    {"bits": None, "topology": "forum", "seed": 1},
    {"bits": 800, "topology": "mesh", "n": 2, "seed": 1},
    {"bits": 800, "topology": "mesh", "n": 5, "seed": 1},
    {"bits": 800, "topology": "mesh", "leader": True, "seed": 1},
    {"bits": 800, "topology": "mesh", "incentive": "desperate", "seed": 1},
    {"bits": 800, "topology": "mesh", "seed": 2},
    {"bits": 0, "topology": "mesh", "seed": 2},
]

BASE = Path(__file__).resolve().parent.parent / "runs" / "lab"
BASE.mkdir(parents=True, exist_ok=True)
res = BASE / "RESULTS.jsonl"
done = set()
if res.exists():
    for line in res.read_text().splitlines():
        try:
            done.add(json.dumps(json.loads(line)["cfg"], sort_keys=True))
        except Exception:
            pass

for cfg in CELLS:
    key = json.dumps({**cfg, "n": cfg.get("n", 3)}, sort_keys=True)
    if key in done:
        continue
    tag = (f"b{cfg.get('bits')}_{cfg.get('topology')}_{cfg.get('incentive','sym')}"
           f"_n{cfg.get('n',3)}{'_lead' if cfg.get('leader') else ''}_s{cfg.get('seed',1)}")
    out = BASE / tag
    t0 = time.time()
    try:
        s = run_cell("qwen3.5:2b", cfg, out, verbose=False)
    except Exception as e:
        print(f"FAIL {tag}: {type(e).__name__}: {e}", flush=True)
        continue
    s["_tag"], s["_secs"] = tag, round(time.time() - t0, 1)
    with res.open("a") as f:
        f.write(json.dumps(s) + "\n")
    print(f"{tag:48s} {s['_secs']:5.0f}s  rub {s['rubric']}  harm {s['harm']:3d}  "
          f"x {s['extraction']:5.2f}  ppm {s['mean_price']}  same {s['identical_price_weeks']}  "
          f"msgs {s['messages']:2d}  bits {s['bits_sent']:4d}  prof {list(s['profit'].values())}",
          flush=True)
print("GRID DONE", flush=True)
