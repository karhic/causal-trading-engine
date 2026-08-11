from datetime import datetime,timezone
from causaltrader import Bar,DataEvent,ReplayEngine,Side,SimBroker,Strategy,TargetPosition
UTC=timezone.utc
class BuyFirstBar(Strategy):
    def on_event(self,ctx,event):
        if not ctx.state.get("sent"): ctx.state["sent"]=True; return (TargetPosition("X",1.0),)
        return ()
def bar_event(day,open_,close):
    t=datetime(2026,1,day,21,tzinfo=UTC); return DataEvent("test","market.bar.1d","X",t,t,Bar(open_,max(open_,close),min(open_,close),close))
def test_order_from_completed_bar_fills_only_on_next_bar_open():
    broker=SimBroker(starting_cash=1000); audit=ReplayEngine(strategy=BuyFirstBar(),broker=broker,events=[bar_event(1,100,101),bar_event(2,110,111)]).run(); fills=[r.payload for r in audit.records if r.kind=="fill"]; assert len(fills)==1; assert fills[0].side is Side.BUY; assert fills[0].price==110
