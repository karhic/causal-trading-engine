from datetime import datetime,timedelta,timezone
from causaltrader import Bar,DataEvent,ReplayEngine,SimBroker,Strategy,TargetPosition
UTC=timezone.utc
class DeterministicStrategy(Strategy):
    name="deterministic"; version="1"
    def on_event(self,ctx,event): return (TargetPosition("X",1 if event.payload.close>100 else 0),)
def make_events():
    t=datetime(2026,1,1,21,tzinfo=UTC); return [DataEvent("x","market.bar.1d","X",t+timedelta(days=i),t+timedelta(days=i),Bar(px,px,px,px)) for i,px in enumerate([99,101,102,98,103])]
def test_same_code_config_data_produces_same_decision_fingerprint():
    a=ReplayEngine(strategy=DeterministicStrategy(),broker=SimBroker(),events=make_events()).run(); b=ReplayEngine(strategy=DeterministicStrategy(),broker=SimBroker(),events=make_events()).run(); assert a.decision_fingerprint()==b.decision_fingerprint()
