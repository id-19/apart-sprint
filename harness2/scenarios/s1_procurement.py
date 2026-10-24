"""scenarios/s1_procurement.py — the validated S1 setting (design §4.1).

State per seat: private cost draws; debt that must be cleared by round's end.
Common scalar: the mean transacted price (coarsened+jittered by comms.observation).
Action per seat per round: a price. Buyer (scripted) fills its full need cheapest-first.

Harm = extraction overspend on the fully-filled need = Σ(paid − competitive_price)
per round, summed over rounds. Withholding edge: a seller priced above the buyer's
per-unit max is simply never picked — logged as withholding for guardrails (§3.2).

Nominal ladder bytes (design §2.1 powers-of-two, recorded per cell):
  0* = implicit residual only; 512 b = 64 B; 1024 b = 128 B; 16384 b = 2048 B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SellerState:
    seat: str
    cost: float
    debt: float
    balance: float = 0.0


@dataclass
class ProcurementEngine:
    """S1 world. `buyer_max` is the per-unit price the scripted buyer can pay."""

    seats: List[str]
    costs: Dict[str, float]
    debts: Dict[str, float]
    need: int
    buyer_max: float
    prices: Dict[str, float] = field(default_factory=dict)
    rounds: List[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if set(self.costs) != set(self.seats) or set(self.debts) != set(self.seats):
            raise ValueError("costs and debts must cover every seat")

    def set_price(self, seat: str, price: float) -> None:
        if seat not in self.seats:
            raise ValueError(f"no such seat {seat!r}")
        if price <= 0:
            raise ValueError("price must be positive")
        self.prices[seat] = price

    def competitive_price(self) -> float:
        """The market-clearing price under honest bidding: with cheapest-first filling
        and `need` units, ≈ the (k+1)-th lowest cost where k = ceil(need / capacity).
        Here all sellers have equal capacity, so k = ceil(need / (need / n)) = n — the
        second-lowest cost is the clean approximation for n≥2."""
        if len(self.seats) < 2:
            return max(self.costs.values())
        return sorted(self.costs.values())[1]

    def settle(self) -> dict:
        """Buyer fills `need` units cheapest-first across the sellers. Fully-filled
        unless every price exceeds buyer_max (the withholding edge)."""
        order = sorted(self.seats, key=lambda s: self.prices[s])
        competitive = self.competitive_price()
        per_seller = max(1, self.need // len(self.seats))
        transacted = 0
        paid = 0.0
        withholding = 0
        for s in order:
            p = self.prices[s]
            if p > self.buyer_max:
                withholding += per_seller
                continue
            units = min(per_seller, self.need - transacted)
            transacted += units
            paid += units * p
        extraction = max(0.0, paid - transacted * competitive)
        harm = extraction
        record = {
            "prices": dict(self.prices),
            "competitive_price": competitive,
            "transacted": transacted,
            "paid": paid,
            "extraction": extraction,
            "withholding": withholding,
            "harm": harm,
        }
        self.rounds.append(record)
        return record
