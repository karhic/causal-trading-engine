from causaltrader import Strategy, TargetWeight

class MacroRegimeShape(Strategy):
    name = "macro_regime_shape"
    version = "0-example"
    def on_event(self,ctx,event):
        if event.dataset != "calendar.month_end": return ()
        inflation=ctx.data.latest("macro.inflation","US"); trend=ctx.data.latest("signal.market_trend","US"); credit=ctx.data.latest("macro.credit","US")
        if not all((inflation,trend,credit)): return ()
        risk_on=bool(trend.payload["risk_on"] and not credit.payload["stress"])
        return (TargetWeight("SPY",1.0 if risk_on else 0.0,reason="point-in-time macro regime"),)
