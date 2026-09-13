from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any


LEDGER_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class AuditRecord:
    seq: int
    timestamp: datetime
    kind: str
    payload: Any


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _encode(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


class AuditLog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.records: list[AuditRecord] = []
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, timestamp: datetime, kind: str, payload: Any) -> AuditRecord:
        record = AuditRecord(len(self.records) + 1, timestamp, kind, payload)
        self.records.append(record)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(_encode(record), sort_keys=True, separators=(",", ":")) + "\n")
        return record

    def decision_fingerprint(self) -> str:
        """Stable representation of economically meaningful decisions.

        Audit timestamps are deliberately excluded. A replay performed later should
        fingerprint identically to the original run if strategy actions, orders and
        fills are identical.
        """
        interesting = [
            {"kind": r.kind, "payload": _encode(r.payload)}
            for r in self.records
            if r.kind in {"strategy_action", "order_submitted", "fill"}
        ]
        return json.dumps(interesting, sort_keys=True, separators=(",", ":"))
