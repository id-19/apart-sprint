# DO NOT USE THESE CELLS

Written 2026-10-24 15:47.

Every directory here was **overwritten** by a later run. `--seeds N` means "run seeds 1..N", so my
rerun loop re-executed seed 1 (and 2) and clobbered the earlier cells. The numbers printed in the
console during those runs no longer match the files on disk:

| cell | printed at run time | what the file now says |
|---|---|---|
| free-s1 | 238.8 | 496.9 |
| silent-s1 | 496.9 | 975.1 |

So the 238.8 observation (a schedule proposed and confirmed, cost halved) **cannot be reproduced from
this directory** — only the transcript I read at the time supports it, and that file has since been
overwritten too.

Also present in these runs: a real engine bug — a voluntary fill on the due day was **double-executed**
by the forced completion (a 10-lot order showing `q=+20`). Fixed in `engine.py`; the same fix is why
these cells are not comparable with `runs/seed_v0b`.

Use `runs/seed_v0b` instead.
