from __future__ import annotations

from abc import ABC
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .account import AccountView
from .data import CausalDataStore
from .models import DataEvent, Fill, StrategyAction


@dataclass(slots=True)
class StrategyContext:
    data: CausalDataStore
    account: AccountView
    state: MutableMapping[str, Any]
    _now: datetime

    @property
    def now(self) -> datetime:
        return self._now

    def _set_now(self, value: datetime) -> None:
        self._now = value


class Strategy(ABC):
    name = "strategy"
    version = "0"

    def initialize(self, ctx: StrategyContext) -> None:
        pass

    def on_event(self, ctx: StrategyContext, event: DataEvent) -> Sequence[StrategyAction]:
        return ()

    def on_fill(self, ctx: StrategyContext, fill: Fill) -> Sequence[StrategyAction]:
        return ()

    def shutdown(self, ctx: StrategyContext) -> None:
        pass
