"""Intraday shape: bar signal + explicit stop-entry execution intent."""
from causaltrader import Bar, OrderIntent, OrderType, Side, Strategy

class BTCNR7Shape(Strategy):
    name = "btc_nr7_shape"
    version = "0-example"
    def on_event(self, ctx, event):
        if event.dataset != "market.bar.15m" or event.instrument != "BTCUSDT": return ()
        bars = [e.payload for e in ctx.data.history("market.bar.15m", "BTCUSDT", count=200) if isinstance(e.payload, Bar)]
        if len(bars) < 200: return ()
        current = bars[-1]
        nr7 = (current.high-current.low) == min(b.high-b.low for b in bars[-7:])
        sma200 = sum(b.close for b in bars)/len(bars)
        if nr7 and current.close > sma200:
            return (OrderIntent("BTCUSDT", Side.BUY, 0.001, OrderType.STOP, stop_price=current.high, tag="nr7-long", reason="NR7 above 200-bar SMA"),)
        return ()
