"""IBKR adapter boundary.

Deliberately dependency-free in v0.1. The engine does not import an IBKR SDK.
Implementations should translate IBKR callbacks into DataEvent and generic Fill/order
models here, leaving strategy code unchanged.

Recommended split when wiring the real account:
    IBKRMarketDataAdapter -> async DataEvent stream
    IBKRBrokerAdapter     -> Broker protocol

Paper/live should differ only in connection/account configuration.
"""

from __future__ import annotations


class IBKRNotConfigured(RuntimeError):
    pass


class IBKRMarketDataAdapter:
    def __init__(self, *args, **kwargs) -> None:
        raise IBKRNotConfigured(
            "IBKR transport is intentionally not bundled in core v0.1. "
            "Add the chosen IBKR client library in this adapter only."
        )


class IBKRBrokerAdapter:
    def __init__(self, *args, **kwargs) -> None:
        raise IBKRNotConfigured(
            "IBKR transport is intentionally not bundled in core v0.1. "
            "Add the chosen IBKR client library in this adapter only."
        )
