from __future__ import annotations

from typing import Iterable, Protocol

from .broker import Broker
from .models import OrderIntent, Side, StrategyAction, TargetPosition, TargetWeight


class Planner(Protocol):
    def plan(self, actions: Iterable[StrategyAction], broker: Broker) -> list[OrderIntent]: ...


class DecisionOnlyPlanner:
    """Log strategy actions without translating them into broker orders."""

    def plan(self, actions: Iterable[StrategyAction], broker: Broker) -> list[OrderIntent]:
        list(actions)
        return []


class ExecutionPlanner:
    def plan(self, actions: Iterable[StrategyAction], broker: Broker) -> list[OrderIntent]:
        out: list[OrderIntent] = []
        for action in actions:
            if isinstance(action, OrderIntent):
                out.append(action)
            elif isinstance(action, TargetPosition):
                current = broker.position(action.instrument).quantity
                delta = action.quantity - current
                if abs(delta) > 1e-12:
                    out.append(OrderIntent(action.instrument, Side.BUY if delta > 0 else Side.SELL, abs(delta), tag=action.tag, reason=action.reason))
            elif isinstance(action, TargetWeight):
                unit_notional = broker.notional_per_unit(action.instrument)
                if unit_notional is None or unit_notional <= 0:
                    raise RuntimeError(f"No current notional for TargetWeight({action.instrument})")
                desired_qty = broker.equity() * action.weight / unit_notional
                current = broker.position(action.instrument).quantity
                delta = desired_qty - current
                if abs(delta) > 1e-12:
                    out.append(OrderIntent(action.instrument, Side.BUY if delta > 0 else Side.SELL, abs(delta), tag=action.tag, reason=action.reason))
            else:
                raise TypeError(type(action))
        return out
