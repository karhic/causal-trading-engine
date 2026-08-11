from datetime import datetime,timezone
from causaltrader import CausalDataStore,SimBroker
from causaltrader.account import AccountView
from causaltrader.clock import ReplayClock
from causaltrader.state import MemoryState
from causaltrader.strategy import StrategyContext
UTC=timezone.utc
def test_strategy_context_does_not_expose_mode_clock_broker_or_audit():
    now=datetime(2026,8,11,tzinfo=UTC); clock=ReplayClock(now); broker=SimBroker(); ctx=StrategyContext(CausalDataStore(clock),AccountView(broker),MemoryState(),now); assert not hasattr(ctx,"mode"); assert not hasattr(ctx,"clock"); assert not hasattr(ctx,"broker"); assert not hasattr(ctx,"audit"); assert ctx.now==now
