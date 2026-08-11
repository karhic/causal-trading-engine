from datetime import datetime,timezone
from causaltrader import DataEvent,FuturesChain
UTC=timezone.utc
def test_futures_chain_resolves_actual_contracts_not_continuous_symbol():
    chain=FuturesChain("CL",("CL-202609","CL-202610","CL-202611")); assert chain.nth(1)=="CL-202609"; assert chain.nth(2)=="CL-202610"; event=DataEvent("ibkr","futures.chain","CL",datetime(2026,8,11,tzinfo=UTC),datetime(2026,8,11,tzinfo=UTC),chain); assert event.payload.nth(1)!=event.instrument
