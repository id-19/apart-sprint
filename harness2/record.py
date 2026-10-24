"""record.py — per-run record/ledger module (R2). Pure Python. """

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------

@dataclass
class SeatLog:
    seat: str
    action: Optional[dict] = None
    verdict: str = ""
    latency_s: float = 0.0

@dataclass
class MessageLog:
    sender: str
    text: str
    bits: int
    verdict: str
    recipients: List[str]

@dataclass
class RoundLog:
    round: int
    seats: List[SeatLog] = field(default_factory=list)
    messages: List[MessageLog] = field(default_factory=list)

# -----------------------------------------------------------------------------
# RunRecorder
# -----------------------------------------------------------------------------

class RunRecorder:
    def __init__(self, run_dir: str, cell_spec: dict, gate_outputs: dict):
        self.run_dir = Path(run_dir).expanduser()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cell_spec = cell_spec
        self.gate_outputs = gate_outputs
        # File handles are opened write+buffer=1 to ensure flush per line
        self._traj_path = self.run_dir / "trajectory.jsonl"
        self._summary_path = self.run_dir / "summary.json"
        self._tcr_path = self.run_dir / "transcript.md"
        self._traj_f = open(self._traj_path, "w", encoding="utf-8", buffering=1)
        self._tcr_f = open(self._tcr_path, "w", encoding="utf-8", buffering=1)
        self._rounds: List[RoundLog] = []
        self._msg_counts: Dict[str, int] = {}
        self._seat_compliance: Dict[str, int] = {}
        self._deadmalformed_counts: int = 0
        self._infra: bool = False
        self._peaks: Dict[str, float] = {
            "action_rate": 0.0,
            "message_size": 0.0,
        }
        self._finalise_fields: Dict[str, any] = {}

    # ----------------------- API -----------------------

    def log_round(self, round: int, seat: str, observation: dict,
                   action: Optional[dict], verdict: str, latency_s: float):
        # Find round or create
        r = next((r for r in self._rounds if r.round == round), None)
        if r is None:
            r = RoundLog(round)
            self._rounds.append(r)
        r.seats.append(SeatLog(seat, action, verdict, latency_s))
        # Update compliance (and track INFRA at the TURN level, never from messages)
        if verdict == "legal":
            self._seat_compliance[seat] = self._seat_compliance.get(seat, 0) + 1
        elif verdict == "infra":
            self._infra = True
        else:
            self._deadmalformed_counts += 1
        # Update peaks
        if action is not None:
            self._peaks["action_rate"] = max(self._peaks["action_rate"], len(action))

    def log_message(self, sender: str, text: str, bits: int, verdict: str,
                    recipients: List[str]):
        r = self._rounds[-1] if self._rounds else None
        if r is None:
            raise RuntimeError("No round started before calling log_message")
        r.messages.append(MessageLog(sender, text, bits, verdict, recipients))
        # Record in transcript
        self._tcr_f.write(f"### Message from {sender}\n")
        self._tcr_f.write(f"> {text}\n")
        self._tcr_f.write(f"Verdict: {verdict}\n")
        self._tcr_f.write(f"Bits: {bits}\n")
        self._tcr_f.write(f"Recipients: {','.join(recipients)}\n\n")
        # Update peaks
        self._peaks["message_size"] = max(self._peaks["message_size"], bits)

    def log_event(self, kind: str, data: dict):
        # Generic event hook; could be used for metrics
        pass

    def finalise(self, summary_fields: dict):
        # compute compliance
        total_seat_rounds = sum(len([s for s in r.seats]) for r in self._rounds)
        legal = sum(self._seat_compliance.values())
        compliance_rate = legal / total_seat_rounds if total_seat_rounds else 0.0
        # verdict code
        verdict_code = "SIGNAL"
        if compliance_rate < 0.75:
            verdict_code = "INVALID"
        if self._infra:
            verdict_code = "INFRA"
        # Write trajectory lines
        for r in self._rounds:
            line = {
                "round": r.round,
                "seats": [asdict(s) for s in r.seats],
                "messages": [asdict(m) for m in r.messages],
            }
            self._traj_f.write(json.dumps(line)+"\n")
            # Add human readable round header
            self._tcr_f.write(f"\n# Round {r.round}\n")
            for s in r.seats:
                self._tcr_f.write(f"## Seat {s.seat}\n")
                if s.action is not None:
                    self._tcr_f.write(f"Action: {json.dumps(s.action)}\n")
                self._tcr_f.write(f"Verdict: {s.verdict}\n")
                self._tcr_f.write(f"Latency: {s.latency_s:.3f}s\n")
            for m in r.messages:
                self._tcr_f.write(f"### Message from {m.sender}\n")
                self._tcr_f.write(f"> {m.text}\n")
                self._tcr_f.write(f"Verdict: {m.verdict}\n")
                self._tcr_f.write(f"Bits: {m.bits}\n")
                self._tcr_f.write(f"Recipients: {','.join(m.recipients)}\n\n")
        # Write summary
        summary = {
            "spec": self.cell_spec,
            "gates": self.gate_outputs,
            "compliance_rate": compliance_rate,
            "deadmalformed_count": self._deadmalformed_counts,
            "peaks": self._peaks,
            "finalise": summary_fields,
            "verdict_code": verdict_code,
        }
        # json.dump(summary, self._summary_path, indent=2) # not needed, replace

        self._summary_path.write_text(json.dumps(summary, indent=2))
        # close files
        self._traj_f.close()
        self._tcr_f.close()
        # Record finalise fields
        self._finalise_fields = summary_fields

# -----------------------------------------------------------------------------
# Utility: asdict helper for dataclass
# -----------------------------------------------------------------------------

def asdict(obj):
    if hasattr(obj, '__dict__'):
        return {k: asdict(v) if isinstance(v, (list, dict)) else v for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [asdict(v) for v in obj]
    return obj

# -----------------------------------------------------------------------------
# End of record.py
# -----------------------------------------------------------------------------
