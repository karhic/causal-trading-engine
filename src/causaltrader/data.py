from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .clock import Clock
from .models import DataEvent


class CausalityViolation(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DataKey:
    dataset: str
    instrument: str | None


class CausalDataStore:
    """Point-in-time data barrier."""

    def __init__(self, clock: Clock, events: Iterable[DataEvent] = ()) -> None:
        self._clock = clock
        self._by_key: dict[DataKey, list[DataEvent]] = defaultdict(list)
        for event in events:
            self.add(event)

    def add(self, event: DataEvent) -> None:
        key = DataKey(event.dataset, event.instrument)
        bucket = self._by_key[key]
        bucket.append(event)
        bucket.sort(key=lambda e: (e.available_at, e.event_time, e.event_id))

    def latest(self, dataset: str, instrument: str | None = None, *, as_of: datetime | None = None) -> DataEvent | None:
        cutoff = self._validated_cutoff(as_of)
        events = self._by_key.get(DataKey(dataset, instrument), ())
        known = [e for e in events if e.available_at <= cutoff]
        if not known:
            return None
        return max(known, key=lambda e: (e.event_time, e.available_at, e.event_id))

    def history(self, dataset: str, instrument: str | None = None, *, count: int | None = None, since: datetime | None = None, as_of: datetime | None = None) -> list[DataEvent]:
        cutoff = self._validated_cutoff(as_of)
        events = self._by_key.get(DataKey(dataset, instrument), ())
        known = [e for e in events if e.available_at <= cutoff and (since is None or e.event_time >= since)]
        known.sort(key=lambda e: (e.event_time, e.available_at, e.event_id))
        return known[-count:] if count is not None else known

    def payload_history(self, *args: Any, **kwargs: Any) -> list[Any]:
        return [e.payload for e in self.history(*args, **kwargs)]

    def _validated_cutoff(self, as_of: datetime | None) -> datetime:
        cutoff = self._clock.now if as_of is None else as_of
        if cutoff > self._clock.now:
            raise CausalityViolation(f"strategy requested data as of {cutoff.isoformat()} while clock is {self._clock.now.isoformat()}")
        return cutoff
