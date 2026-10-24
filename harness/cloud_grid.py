"""cloud_grid.py — the bit-rate matrix on a cheap cloud model, with a hard cost ceiling.

Cells are one seed each: the point is the shape of the bit-rate response, not a variance estimate.
Adds the structural axes the task asked for (hierarchy, size, incentive) at the two informative budgets.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab import run_cell

MODEL = sys.argv[1] if len(sys.argv) > 1 else "glm-5.3-flash:cloud"
CEILING = 4.0          # hard stop, leaves headroom under the $5 cap

CELLS = [
    # the bit-rate curve, 3 sellers, mesh — two seeds at each budget
    {"bits": 0, "topology": "mesh", "seed": 1},
    {"bits": 0, "topology": "mesh", "seed": 2},
    {"bits": 80, "topology": "mesh", "seed": 1},
    {"bits": 80, "topology": "mesh", "seed": 2},
    {"bits": 800, "topology": "mesh", "seed": 1},
    {"bits": 800, "topology": "mesh", "seed": 2},
    # topology contrast at the wide budget
    {"bits": 800, "topology": "forum", "seed": 1},
    # cheapest possible channel: a leader's published price, no messages needed
    {"bits": 80, "topology": "mesh", "leader": True, "seed": 1},
    # size
    {"bits": 800, "topology": "mesh", "n": 5, "seed": 1},
]

BASE = Path(__file__).resolve().parent.parent / "runs" / "cloud"
BASE.mkdir(parents=True, exist_ok=True)
res = BASE / "RESULTS.jsonl"
spent = 0.0

for cfg in CELLS:
    tag = (f"b{cfg.get('bits')}_{cfg.get('topology')}"
           f"{'_lead' if cfg.get('leader') else ''}"
           f"{'_desp' if cfg.get('incentive') == 'desperate' else ''}"
           f"_n{cfg.get('n', 3)}_s{cfg.get('seed')}")
    out = BASE / tag
    if (out / "summary.json").exists():
        spent += json.loads((out / "summary.json").read_text()).get("cost_usd", 0) or 0
        continue
    t0 = time.time()
    try:
        s = run_cell(MODEL, cfg, out, verbose=False)
    except Exception as e:
        print(f"FAIL {tag}: {type(e).__name__}: {e}", flush=True)
        continue
    s["_tag"], s["_secs"] = tag, round(time.time() - t0, 1)
    spent += s.get("cost_usd") or 0
    with res.open("a") as f:
        f.write(json.dumps(s) + "\n")
    print(f"{tag:34s} {s['_secs']:5.0f}s rub {s['rubric']} comp {s['compliance']:.2f} "
          f"harm {s['harm']:3d} ppm {str(s['mean_price']):>5} same {s['identical_price_weeks']} "
          f"msgs {s['messages']:2d} bits {s['bits_sent']:5d} tok {s['in_tokens']}/{s['out_tokens']} "
          f"${s['cost_usd']:.3f} | total ${spent:.2f}", flush=True)
    if spent > CEILING:
        print(f"STOP: spent ${spent:.2f} > ceiling ${CEILING}", flush=True)
        break
print(f"GRID DONE spent ${spent:.2f}", flush=True)
