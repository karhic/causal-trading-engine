from datetime import datetime,timedelta,timezone
import json
from causaltrader import Bar,DataEvent,ReplayEngine,SimBroker,Strategy,TargetPosition
from causaltrader.audit import _encode
UTC=timezone.utc
class CausalTrend(Strategy):
    def on_event(self,ctx,event):
        if event.dataset!="market.bar.1d": return ()
        bars=[e.payload for e in ctx.data.history("market.bar.1d","X",count=3)]
        if len(bars)<3: return ()
        return (TargetPosition("X",1.0 if bars[-1].close>bars[-2].close else 0.0),)
def events(n=8):
    t0=datetime(2026,1,1,21,tzinfo=UTC); closes=[100,101,99,102,101,104,103,106][:n]; return [DataEvent("test","market.bar.1d","X",t0+timedelta(days=i),t0+timedelta(days=i),Bar(c,c+1,c-1,c)) for i,c in enumerate(closes)]
def decisions(audit,cutoff): return json.dumps([_encode(r) for r in audit.records if r.timestamp<=cutoff and r.kind in {"strategy_action","order_submitted","fill"}],sort_keys=True,separators=(",",":"))
def test_appending_future_data_cannot_change_past_decisions():
    p=events(5); f=events(8); cutoff=p[-1].available_at; a=ReplayEngine(strategy=CausalTrend(),broker=SimBroker(),events=p).run(); b=ReplayEngine(strategy=CausalTrend(),broker=SimBroker(),events=f).run(); assert decisions(a,cutoff)==decisions(b,cutoff)
