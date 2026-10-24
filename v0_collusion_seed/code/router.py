"""router.py — the swarm-wide bit budget.

Two allocation rules, because they are different experiments:

  pool   — one shared bucket per day for the whole swarm. First come, first served.
           This is the literal reading of "bandwidth available to the entire swarm":
           when the budget is small, seats compete for it, and *who gets to speak*
           becomes part of the problem.

  share  — the day's budget split equally per seat. Aggregate == per-seat x seats,
           so this isolates bandwidth from contention and is the identification control.

Over-budget messages are dropped and counted, never truncated.
"""
from __future__ import annotations


class SwarmRouter:
    def __init__(self, bits_per_day: int, n_seats: int, mode: str = "pool"):
        assert mode in ("pool", "share")
        self.bits_per_day = int(bits_per_day)
        self.n_seats = n_seats
        self.mode = mode
        self.reset_day()

    def reset_day(self):
        self.left = self.bits_per_day
        self.log = []          # per (seat, message) outcome rows

    @property
    def share(self) -> int:
        return self.bits_per_day // max(1, self.n_seats)

    def admit(self, seat: int, message: str) -> tuple[str, list[str]]:
        """Returns (message_kept, flags). Empty messages are always admitted."""
        msg = message or ""
        need = 8 * len(msg.encode("utf-8"))
        flags = []
        if need == 0:
            self.log.append({"seat": seat, "bits": 0, "ok": True, "flags": []})
            return "", flags
        if self.mode == "share" and need > self.share:
            flags.append("over_share_drop")
        if need > self.left:
            flags.append("over_pool_drop" if self.mode == "pool" else "over_budget_drop")
        if flags:
            self.log.append({"seat": seat, "bits": need, "ok": False, "flags": flags})
            return "", flags
        self.left -= need
        self.log.append({"seat": seat, "bits": need, "ok": True, "flags": []})
        return msg, flags

    def day_stats(self) -> dict:
        att = sum(r["bits"] for r in self.log)
        acc = sum(r["bits"] for r in self.log if r["ok"])
        return {"attempted_bits": att, "admitted_bits": acc,
                "budget_bits": self.bits_per_day, "mode": self.mode,
                "utilised": round(acc / self.bits_per_day, 3) if self.bits_per_day else 0.0,
                "drops": sum(1 for r in self.log if not r["ok"])}
