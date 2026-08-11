from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable

from .models import Bar, DataEvent, FuturesChain, Quote


def _payload_to_wire(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Bar):
        return {"type": "Bar", "value": asdict(payload)}
    if isinstance(payload, Quote):
        return {"type": "Quote", "value": asdict(payload)}
    if isinstance(payload, FuturesChain):
        value = asdict(payload)
        value["contracts"] = list(payload.contracts)
        return {"type": "FuturesChain", "value": value}
    if is_dataclass(payload):
        return {"type": "dataclass", "class": type(payload).__name__, "value": asdict(payload)}
    return {"type": "json", "value": payload}


def _payload_from_wire(wire: dict[str, Any]) -> Any:
    kind, value = wire["type"], wire["value"]
    if kind == "Bar":
        return Bar(**value)
    if kind == "Quote":
        return Quote(**value)
    if kind == "FuturesChain":
        return FuturesChain(value["root"], tuple(value["contracts"]))
    return value


def event_to_wire(event: DataEvent) -> dict[str, Any]:
    return {
        "source": event.source,
        "dataset": event.dataset,
        "instrument": event.instrument,
        "event_time": event.event_time.isoformat(),
        "available_at": event.available_at.isoformat(),
        "payload": _payload_to_wire(event.payload),
        "metadata": dict(event.metadata),
        "event_id": event.event_id,
    }


def event_from_wire(wire: dict[str, Any]) -> DataEvent:
    return DataEvent(
        source=wire["source"],
        dataset=wire["dataset"],
        instrument=wire["instrument"],
        event_time=datetime.fromisoformat(wire["event_time"]),
        available_at=datetime.fromisoformat(wire["available_at"]),
        payload=_payload_from_wire(wire["payload"]),
        metadata=wire.get("metadata", {}),
        event_id=wire["event_id"],
    )


class JsonlEventArchive:
    """Append every live input event; the file itself can later feed ReplayEngine."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: DataEvent) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event_to_wire(event), sort_keys=True, separators=(",", ":")) + "\n")

    def read(self) -> list[DataEvent]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            return [event_from_wire(json.loads(line)) for line in fh if line.strip()]

    def __iter__(self) -> Iterable[DataEvent]:
        return iter(self.read())
