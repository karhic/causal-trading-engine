from datetime import datetime,timedelta,timezone
import pytest
from causaltrader import CausalDataStore,CausalityViolation,DataEvent
from causaltrader.clock import ReplayClock
UTC=timezone.utc
def test_future_observation_is_in_store_but_invisible_until_available():
    now=datetime(2026,1,1,12,tzinfo=UTC); clock=ReplayClock(now); future=DataEvent("macro","macro.cpi","US",datetime(2025,12,1,tzinfo=UTC),now+timedelta(days=10),{"value":3.1}); store=CausalDataStore(clock,[future]); assert store.latest("macro.cpi","US") is None
    with pytest.raises(CausalityViolation): store.latest("macro.cpi","US",as_of=now+timedelta(seconds=1))
    clock.advance(future.available_at); assert store.latest("macro.cpi","US")==future
def test_revised_observation_does_not_replace_original_before_revision_time():
    t0=datetime(2026,1,1,tzinfo=UTC); clock=ReplayClock(t0); first=DataEvent("macro","macro.payrolls","US",t0,t0,{"value":100}); revision=DataEvent("macro","macro.payrolls","US",t0,t0+timedelta(days=30),{"value":80,"revision":1}); store=CausalDataStore(clock,[first,revision]); assert store.latest("macro.payrolls","US").payload["value"]==100; clock.advance(t0+timedelta(days=30)); assert store.latest("macro.payrolls","US").payload["value"]==80
