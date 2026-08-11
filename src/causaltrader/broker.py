from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
from typing import Protocol

from .models import Bar, DataEvent, Fill, InstrumentSpec, OrderIntent, OrderType, Position, Side


class Broker(Protocol):
    def submit(self, order: OrderIntent, now: datetime) -> str: ...
    def on_data_event(self, event: DataEvent) -> list[Fill]: ...
    def position(self, instrument: str) -> Position: ...
    def positions(self) -> dict[str, Position]: ...
    def equity(self) -> float: ...
    def last_price(self, instrument: str) -> float | None: ...
    def notional_per_unit(self, instrument: str) -> float | None: ...


@dataclass(slots=True)
class PendingOrder:
    order_id: str
    intent: OrderIntent
    submitted_at: datetime


class SimBroker:
    """Causal bar simulator.

    Orders submitted in response to a completed bar are not considered for a fill
    until a later bar event arrives. This prevents same-bar close/high/low leakage.
    """

    def __init__(
        self,
        *,
        starting_cash: float = 100_000.0,
        commission_per_unit: float = 0.0,
        slippage_bps: float = 0.0,
        instrument_specs: dict[str, InstrumentSpec] | None = None,
    ) -> None:
        self.cash = float(starting_cash)
        self.commission_per_unit = float(commission_per_unit)
        self.slippage_bps = float(slippage_bps)
        self.instrument_specs = instrument_specs or {}
        self._positions: dict[str, Position] = {}
        self._pending: list[PendingOrder] = []
        self._last_prices: dict[str, float] = {}
        self._order_counter = 0
        self._client_order_ids: dict[str, str] = {}

    def submit(self, order: OrderIntent, now: datetime) -> str:
        if order.client_order_id and order.client_order_id in self._client_order_ids:
            return self._client_order_ids[order.client_order_id]
        self._order_counter += 1
        raw = f"{self._order_counter}|{now.isoformat()}|{order.instrument}|{order.side.value}|{order.quantity}|{order.tag}"
        order_id = hashlib.sha256(raw.encode()).hexdigest()[:18]
        self._pending.append(PendingOrder(order_id, order, now))
        if order.client_order_id:
            self._client_order_ids[order.client_order_id] = order_id
        return order_id

    def on_data_event(self, event: DataEvent) -> list[Fill]:
        if not isinstance(event.payload, Bar) or event.instrument is None:
            return []
        bar = event.payload
        self._last_prices[event.instrument] = bar.close
        fills: list[Fill] = []
        keep: list[PendingOrder] = []
        for pending in self._pending:
            order = pending.intent
            if order.instrument != event.instrument:
                keep.append(pending)
                continue
            if event.available_at <= pending.submitted_at:
                keep.append(pending)
                continue
            if order.valid_until is not None and event.available_at > order.valid_until:
                continue
            price = self._fill_price(order, bar)
            if price is None:
                keep.append(pending)
                continue
            commission = abs(order.quantity) * self.commission_per_unit
            fill = Fill(
                order_id=pending.order_id,
                instrument=order.instrument,
                side=order.side,
                quantity=order.quantity,
                price=price,
                commission=commission,
                timestamp=event.available_at,
                tag=order.tag,
            )
            self._apply_fill(fill)
            fills.append(fill)
        self._pending = keep
        return fills

    def _fill_price(self, order: OrderIntent, bar: Bar) -> float | None:
        if order.order_type is OrderType.MARKET:
            raw = bar.open
        elif order.order_type is OrderType.LIMIT:
            assert order.limit_price is not None
            if order.side is Side.BUY:
                if bar.low > order.limit_price:
                    return None
                raw = min(bar.open, order.limit_price)
            else:
                if bar.high < order.limit_price:
                    return None
                raw = max(bar.open, order.limit_price)
        elif order.order_type is OrderType.STOP:
            assert order.stop_price is not None
            if order.side is Side.BUY:
                if bar.high < order.stop_price:
                    return None
                raw = max(bar.open, order.stop_price)
            else:
                if bar.low > order.stop_price:
                    return None
                raw = min(bar.open, order.stop_price)
        else:
            raise ValueError(order.order_type)
        slip = raw * self.slippage_bps / 10_000.0
        return raw + slip if order.side is Side.BUY else raw - slip

    def _apply_fill(self, fill: Fill) -> None:
        spec = self.instrument_specs.get(fill.instrument, InstrumentSpec(fill.instrument))
        signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
        pos = self._positions.setdefault(fill.instrument, Position(fill.instrument))
        self.cash -= signed * fill.price * spec.multiplier
        self.cash -= fill.commission
        old_qty = pos.quantity
        new_qty = old_qty + signed
        if old_qty == 0 or (old_qty > 0) == (signed > 0):
            total_abs = abs(old_qty) + abs(signed)
            pos.average_price = ((abs(old_qty) * pos.average_price + abs(signed) * fill.price) / total_abs if total_abs else 0.0)
        else:
            closed_qty = min(abs(old_qty), abs(signed))
            direction = 1.0 if old_qty > 0 else -1.0
            pos.realized_pnl += closed_qty * (fill.price - pos.average_price) * direction * spec.multiplier
            if new_qty == 0:
                pos.average_price = 0.0
            elif (new_qty > 0) != (old_qty > 0):
                pos.average_price = fill.price
        pos.quantity = new_qty

    def position(self, instrument: str) -> Position:
        pos = self._positions.get(instrument)
        return replace(pos) if pos else Position(instrument)

    def positions(self) -> dict[str, Position]:
        return {k: replace(v) for k, v in self._positions.items()}

    def last_price(self, instrument: str) -> float | None:
        return self._last_prices.get(instrument)

    def notional_per_unit(self, instrument: str) -> float | None:
        px = self.last_price(instrument)
        if px is None:
            return None
        spec = self.instrument_specs.get(instrument, InstrumentSpec(instrument))
        return px * spec.multiplier

    def equity(self) -> float:
        value = self.cash
        for instrument, pos in self._positions.items():
            px = self._last_prices.get(instrument, pos.average_price)
            spec = self.instrument_specs.get(instrument, InstrumentSpec(instrument))
            value += pos.quantity * px * spec.multiplier
        return value
