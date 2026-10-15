"""Append-only, hash-chained audit log (FR-7, ADR-003).

Each line is a JSON event. `hash` = sha256(canonical JSON of the event without
`hash`), and every event carries `prev_hash`, so editing or deleting any line
breaks verification from that point on.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opc_guard.errors import AuditError

GENESIS = "0" * 64


def _digest(event: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self.seq = 0
        self.prev_hash = GENESIS
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AuditError(f"could not create audit directory: {exc}") from exc

    def append(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event: dict[str, Any] = {
            "seq": self.seq,
            "run_id": self.run_id,
            "type": event_type,
            "ts": round(time.time(), 3),
            "data": data,
            "prev_hash": self.prev_hash,
        }
        event["hash"] = _digest({k: v for k, v in event.items() if k != "hash"})
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
                fh.flush()
        except OSError as exc:
            raise AuditError(f"could not write audit event: {exc}") from exc
        self.seq += 1
        self.prev_hash = event["hash"]
        return event


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    events: int
    error: str | None = None


def verify(path: Path) -> VerifyResult:
    """Recompute the chain. Returns the first break found, if any."""
    prev = GENESIS
    count = 0
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return VerifyResult(False, count, f"line {lineno}: not valid JSON")
            if event.get("seq") != count:
                return VerifyResult(False, count, f"line {lineno}: sequence gap (expected {count})")
            if event.get("prev_hash") != prev:
                return VerifyResult(False, count, f"line {lineno}: prev_hash mismatch")
            if _digest({k: v for k, v in event.items() if k != "hash"}) != event.get("hash"):
                return VerifyResult(False, count, f"line {lineno}: hash mismatch (content altered)")
            prev = event["hash"]
            count += 1
    return VerifyResult(True, count)
