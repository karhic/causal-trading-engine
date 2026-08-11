from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class FuturesChain:
    root: str
    contracts: tuple[str, ...]

    def nth(self, n: int) -> str:
        if n < 1:
            raise ValueError("futures chain is 1-indexed")
        try:
            return self.contracts[n - 1]
        except IndexError as exc:
            raise IndexError(f"{self.root} has no contract #{n}") from exc


@dataclass(frozen=True, slots=True)
class Quote:
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0


@dataclass(frozen=True, slots=True)
class DataEvent:
    source: str
    dataset: str
    instrument: str | None
    event_time: datetime
    available_at: datetime
    payload: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = ""

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.event_time.tzinfo is None:
            raise ValueError("event_time and available_at must be timezone-aware")
        if not self.event_id:
            raw = canonical_json({"source": self.source, "dataset": self.dataset, "instrument": self.instrument, "event_time": self.event_time, "available_at": self.available_at, "payload": self.payload, "metadata": self.metadata}).encode()
            object.__setattr__(self, "event_id", hashlib.sha256(raw).hexdigest()[:24])


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    instrument: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    valid_until: datetime | None = None
    tag: str = ""
    reason: str = ""
    client_order_id: str = ""

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price required for LIMIT")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("stop_price required for STOP")


@dataclass(frozen=True, slots=True)
class TargetPosition:
    instrument: str
    quantity: float
    tag: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class TargetWeight:
    instrument: str
    weight: float
    tag: str = ""
    reason: str = ""


StrategyAction = OrderIntent | TargetPosition | TargetWeight


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    instrument: str
    side: Side
    quantity: float
    price: float
    commission: float
    timestamp: datetime
    tag: str = ""


@dataclass(slots=True)
class Position:
    instrument: str
    quantity: float = 0.0
    average_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    instrument: str
    multiplier: float = 1.0
    tick_size: float = 0.01
    currency: str = "USD"
    asset_class: str = "unknown"
