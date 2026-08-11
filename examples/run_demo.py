from datetime import datetime,timedelta,timezone
from causaltrader import Bar,DataEvent,ReplayEngine,SimBroker,Strategy,TargetPosition
UTC=timezone.utc
class ThreeBarTrend(Strategy):
    name="three_bar_trend"; version="1"
    def on_event(self,ctx,event):
        if event.dataset!="market.bar.1d" or event.instrument!="DEMO": return ()
        bars=[e.payload for e in ctx.data.history("market.bar.1d","DEMO",count=3)]
        if len(bars)<3: return ()
        return (TargetPosition("DEMO",1.0 if bars[-1].close>sum(b.close for b in bars)/3 else 0.0,reason="close vs 3-bar mean"),)
def make_events():
    out=[]; start=datetime(2026,1,1,21,tzinfo=UTC)
    for i,close in enumerate([100,99,102,103,101,105]):
        t=start+timedelta(days=i); out.append(DataEvent("demo","market.bar.1d","DEMO",t,t,Bar(close-1,close+1,close-2,close,1000)))
    return out
if __name__=="__main__":
    broker=SimBroker(starting_cash=10000); audit=ReplayEngine(strategy=ThreeBarTrend(),broker=broker,events=make_events()).run(); print("equity:",round(broker.equity(),2)); print("position:",broker.position("DEMO")); print("audit records:",len(audit.records))
