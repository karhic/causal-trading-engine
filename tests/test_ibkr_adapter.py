from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from causaltrader.adapters.ibkr import (
    IBKRBrokerAdapter,
    IBKRContractSpec,
    IBKRSafetyError,
)
from causaltrader.models import Bar, DataEvent, OrderIntent, Side


def make_adapter(*, read_only=True):
    adapter = IBKRBrokerAdapter(
        contracts={
            "SPY": IBKRContractSpec(
                symbol="SPY",
                sec_type="STK",
                exchange="SMART",
                currency="USD",
                primary_exchange="ARCA",
            )
        },
        account="DU12345",
        allowed_accounts={"DU12345"},
        read_only=read_only,
    )
    adapter._managed_accounts = ("DU12345",)
    adapter._next_order_id = 100
    return adapter


def test_read_only_refuses_order_before_touching_transport():
    adapter = make_adapter(read_only=True)
    order = OrderIntent(instrument="SPY", side=Side.BUY, quantity=1)
    with pytest.raises(IBKRSafetyError, match="read-only"):
        adapter.submit(order, datetime.now(UTC))


def test_unexpected_managed_account_is_rejected():
    adapter = make_adapter()
    adapter._managed_accounts = ("DU99999",)
    with pytest.raises(IBKRSafetyError, match="unexpected IBKR account"):
        adapter._validate_account_scope()


def test_exec_details_becomes_one_deduplicated_generic_fill():
    adapter = make_adapter()
    adapter._order_intents[42] = OrderIntent(
        instrument="SPY",
        side=Side.BUY,
        quantity=2,
        tag="unit-test",
    )
    contract = SimpleNamespace(
        symbol="SPY",
        secType="STK",
        lastTradeDateOrContractMonth="",
        multiplier="",
    )
    execution = SimpleNamespace(
        execId="abc.1",
        orderId=42,
        side="BOT",
        shares=2,
        price=500.25,
        time="20260814 14:30:01",
    )

    adapter._on_exec_details(1, contract, execution)
    adapter._on_exec_details(1, contract, execution)
    fills = adapter.poll_fills()

    assert len(fills) == 1
    fill = fills[0]
    assert fill.order_id == "42"
    assert fill.instrument == "SPY"
    assert fill.side is Side.BUY
    assert fill.quantity == 2
    assert fill.price == 500.25
    assert fill.tag == "unit-test"
    assert fill.timestamp.tzinfo is not None


def test_engine_event_updates_last_price_and_drains_fills():
    adapter = make_adapter()
    event = DataEvent(
        source="test",
        dataset="bars",
        instrument="SPY",
        event_time=datetime(2026, 8, 14, 14, 30, tzinfo=UTC),
        available_at=datetime(2026, 8, 14, 14, 31, tzinfo=UTC),
        payload=Bar(open=500.0, high=502.0, low=499.0, close=501.0),
    )
    assert adapter.on_data_event(event) == []
    assert adapter.last_price("SPY") == 501.0
    assert adapter.notional_per_unit("SPY") == 501.0
