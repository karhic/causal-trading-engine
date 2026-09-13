from __future__ import annotations

from collections.abc import AsyncIterable, Iterable, MutableMapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .account import AccountView
from .archive import JsonlEventArchive
from .audit import AuditLog
from .broker import Broker
from .clock import ReplayClock, WallClock
from .data import CausalDataStore
from .models import DataEvent, StrategyAction
from .portfolio import ExecutionPlanner, Planner
from .state import MemoryState
from .strategy import Strategy, StrategyContext


@dataclass(frozen=True, slots=True)
class RunManifest:
    strategy_name: str
    strategy_version: str
    mode: str
    config: dict[str, Any]
    data_sources: tuple[str, ...] = ()
    code_revision: str = "unknown"


class EngineCore:
    def __init__(self, *, strategy: Strategy, clock, data: CausalDataStore, broker: Broker, mode: str, audit: AuditLog | None = None, state: MutableMapping[str, Any] | None = None, planner: Planner | None = None, manifest: RunManifest | None = None, event_archive: JsonlEventArchive | None = None) -> None:
        self.strategy = strategy
        self.clock = clock
        self.data = data
        self.broker = broker
        self.audit = audit or AuditLog()
        self.state = state if state is not None else MemoryState()
        self.planner = planner or ExecutionPlanner()
        self.ctx = StrategyContext(data, AccountView(broker), self.state, clock.now)
        self.manifest = manifest or RunManifest(strategy.name, strategy.version, mode, {})
        self.event_archive = event_archive
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self.audit.write(self.clock.now, "run_manifest", self.manifest)
        self.strategy.initialize(self.ctx)
        self._initialized = True

    def process(self, event: DataEvent) -> None:
        self.initialize()
        self.ctx._set_now(self.clock.now)
        if self.event_archive is not None:
            self.event_archive.append(event)
        self.data.add(event)
        self.audit.write(self.clock.now, "data_event", event)
        fills = self.broker.on_data_event(event)
        for fill in fills:
            self.audit.write(self.clock.now, "fill", fill)
            self._submit_actions(self.strategy.on_fill(self.ctx, fill), origin=f"fill:{fill.order_id}")
        self._submit_actions(self.strategy.on_event(self.ctx, event), origin=f"event:{event.event_id}")
        flush = getattr(self.state, "flush", None)
        if callable(flush):
            flush()

    def _submit_actions(self, actions: Sequence[StrategyAction] | Iterable[StrategyAction], *, origin: str) -> None:
        actions = list(actions)
        for action in actions:
            self.audit.write(self.clock.now, "strategy_action", action)
        for i, order in enumerate(self.planner.plan(actions, self.broker)):
            if not order.client_order_id:
                order = replace(order, client_order_id=f"{self.strategy.name}:{self.strategy.version}:{origin}:{i}")
            order_id = self.broker.submit(order, self.clock.now)
            self.audit.write(self.clock.now, "order_submitted", {"order_id": order_id, "order": order})

    def shutdown(self) -> None:
        if self._initialized:
            self.strategy.shutdown(self.ctx)
            flush = getattr(self.state, "flush", None)
            if callable(flush):
                flush()


class ReplayEngine:
    def __init__(self, *, strategy: Strategy, broker: Broker, events: Iterable[DataEvent], audit: AuditLog | None = None, state: MutableMapping[str, Any] | None = None, config: dict[str, Any] | None = None, code_revision: str = "unknown", planner: Planner | None = None) -> None:
        ordered = sorted(events, key=lambda e: (e.available_at, e.event_time, e.event_id))
        if not ordered:
            raise ValueError("ReplayEngine requires at least one event")
        self.events = ordered
        self.clock = ReplayClock(ordered[0].available_at)
        self.data = CausalDataStore(self.clock)
        sources = tuple(sorted({e.source for e in ordered}))
        self.core = EngineCore(strategy=strategy, clock=self.clock, data=self.data, broker=broker, mode="backtest", audit=audit, state=state, planner=planner, manifest=RunManifest(strategy.name, strategy.version, "backtest", config or {}, sources, code_revision))

    @property
    def audit(self) -> AuditLog:
        return self.core.audit

    def run(self) -> AuditLog:
        self.core.initialize()
        for event in self.events:
            self.clock.advance(event.available_at)
            self.core.process(event)
        self.core.shutdown()
        return self.core.audit


class LiveEngine:
    def __init__(self, *, strategy: Strategy, broker: Broker, audit: AuditLog | None = None, state: MutableMapping[str, Any] | None = None, config: dict[str, Any] | None = None, code_revision: str = "unknown", mode: str = "paper", event_archive: JsonlEventArchive | None = None, planner: Planner | None = None) -> None:
        if mode not in {"paper", "live"}:
            raise ValueError("LiveEngine mode must be paper or live")
        self.clock = WallClock()
        self.data = CausalDataStore(self.clock)
        self.core = EngineCore(strategy=strategy, clock=self.clock, data=self.data, broker=broker, mode=mode, audit=audit, state=state, planner=planner, manifest=RunManifest(strategy.name, strategy.version, mode, config or {}, (), code_revision), event_archive=event_archive)

    async def run(self, source: AsyncIterable[DataEvent]) -> AuditLog:
        self.core.initialize()
        async for event in source:
            if event.available_at > self.clock.now:
                raise RuntimeError(f"provider emitted future event {event.event_id}: {event.available_at.isoformat()} > {self.clock.now.isoformat()}")
            self.core.process(event)
        self.core.shutdown()
        return self.core.audit
