"""Binance adapter boundary.

The existing Binance paper trader can be wrapped behind these interfaces without
changing its signal logic. Keep exchange-specific symbol mapping, websocket parsing,
fee tiers, and order IDs here rather than in a strategy.
"""

from __future__ import annotations


class BinanceNotConfigured(RuntimeError):
    pass


class BinanceMarketDataAdapter:
    def __init__(self, *args, **kwargs) -> None:
        raise BinanceNotConfigured("Wrap the existing Binance feed here.")


class BinanceBrokerAdapter:
    def __init__(self, *args, **kwargs) -> None:
        raise BinanceNotConfigured("Wrap the existing Binance paper/live execution here.")
