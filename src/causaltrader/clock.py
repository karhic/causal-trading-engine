from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    @property
    def now(self) -> datetime: ...


@dataclass
class ReplayClock:
    _now: datetime

    def __post_init__(self) -> None:
        if self._now.tzinfo is None:
            raise ValueError("ReplayClock requires a timezone-aware datetime")

    @property
    def now(self) -> datetime:
        return self._now

    def advance(self, to: datetime) -> None:
        if to.tzinfo is None:
            raise ValueError("ReplayClock requires timezone-aware datetimes")
        if to < self._now:
            raise ValueError(f"clock cannot move backwards: {to} < {self._now}")
        self._now = to


class WallClock:
    @property
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
