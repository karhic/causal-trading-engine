from __future__ import annotations

from .broker import Broker
from .models import Position


class AccountView:
    """Read-only, broker-neutral account facade exposed to strategies."""

    __slots__ = ("__broker",)

    def __init__(self, broker: Broker) -> None:
        self.__broker = broker

    def position(self, instrument: str) -> Position:
        return self.__broker.position(instrument)

    def positions(self) -> dict[str, Position]:
        return self.__broker.positions()

    def equity(self) -> float:
        return self.__broker.equity()

    def last_price(self, instrument: str) -> float | None:
        return self.__broker.last_price(instrument)

    def notional_per_unit(self, instrument: str) -> float | None:
        return self.__broker.notional_per_unit(instrument)
