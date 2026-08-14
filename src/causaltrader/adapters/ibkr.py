"""Interactive Brokers TWS/IB Gateway adapter.

The engine-facing class in this module implements the generic ``Broker`` protocol.
All IBKR SDK imports are lazy so the causal engine remains dependency-free for
backtests.  Install the official TWS API Python client from the IBKR API bundle on
hosts that actually connect to IB Gateway/TWS.

Safety defaults are intentionally restrictive:

* ``read_only=True`` refuses every order submission in-process.
* contracts must be declared explicitly in ``contracts``; root/continuous symbols
  are never guessed into tradable contracts.
* ``allowed_accounts`` can pin the adapter to the expected paper account(s).
* executions are converted to generic ``Fill`` objects from ``execDetails`` rather
  than inferred from the potentially duplicated/incomplete ``orderStatus`` stream.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import math
import threading
import time
from typing import Any, Mapping

from ..models import DataEvent, Fill, OrderIntent, OrderType, Position, Side


class IBKRNotConfigured(RuntimeError):
    pass


class IBKRConnectionError(RuntimeError):
    pass


class IBKRSafetyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IBKRContractSpec:
    """Explicit translation from an engine instrument to an IBKR contract."""

    symbol: str
    sec_type: str
    exchange: str = "SMART"
    currency: str = "USD"
    primary_exchange: str = ""
    last_trade_date_or_contract_month: str = ""
    multiplier: str = ""
    local_symbol: str = ""
    trading_class: str = ""


class IBKRBrokerAdapter:
    """Synchronous engine-facing broker backed by IB Gateway/TWS callbacks.

    IBKR's network loop runs in a daemon thread. Callback state is protected by a
    lock and copied on read. ``on_data_event`` drains fills accumulated since the
    previous engine event, preserving the current Broker protocol without exposing
    IBKR callback objects to strategies.
    """

    def __init__(
        self,
        *,
        contracts: Mapping[str, IBKRContractSpec],
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 17,
        account: str | None = None,
        allowed_accounts: set[str] | None = None,
        read_only: bool = True,
        connect_timeout: float = 10.0,
    ) -> None:
        if not contracts:
            raise ValueError("IBKRBrokerAdapter requires at least one explicit contract")
        if port <= 0:
            raise ValueError("port must be positive")
        self.contracts = dict(contracts)
        self.host = host
        self.port = int(port)
        self.client_id = int(client_id)
        self.account = account
        self.allowed_accounts = set(allowed_accounts or ())
        self.read_only = bool(read_only)
        self.connect_timeout = float(connect_timeout)

        self._lock = threading.RLock()
        self._connected = threading.Event()
        self._positions_end = threading.Event()
        self._account_ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._app: Any | None = None
        self._managed_accounts: tuple[str, ...] = ()
        self._positions: dict[str, Position] = {}
        self._account_values: dict[str, float] = {}
        self._last_prices: dict[str, float] = {}
        self._fills: deque[Fill] = deque()
        self._execution_ids: set[str] = set()
        self._order_intents: dict[int, OrderIntent] = {}
        self._client_order_ids: dict[str, str] = {}
        self._next_order_id: int | None = None
        self._request_id = 10_000

    # ---------- lifecycle ----------

    def connect(self) -> None:
        if self._app is not None:
            return
        app = _build_ib_app(self)
        self._app = app
        try:
            app.connect(self.host, self.port, self.client_id)
        except Exception as exc:
            self._app = None
            raise IBKRConnectionError(
                f"failed to connect to IBKR at {self.host}:{self.port}"
            ) from exc
        self._thread = threading.Thread(target=app.run, name="ibkr-api", daemon=True)
        self._thread.start()
        if not self._connected.wait(self.connect_timeout):
            self.disconnect()
            raise IBKRConnectionError(
                f"IBKR did not deliver nextValidId within {self.connect_timeout:.1f}s"
            )
        self._validate_account_scope()
        self.refresh_account(timeout=self.connect_timeout)
        self.refresh_positions(timeout=self.connect_timeout)

    def disconnect(self) -> None:
        app = self._app
        self._app = None
        if app is not None:
            try:
                app.disconnect()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._connected.clear()

    @property
    def connected(self) -> bool:
        app = self._app
        return bool(app is not None and app.isConnected() and self._connected.is_set())

    @property
    def managed_accounts(self) -> tuple[str, ...]:
        with self._lock:
            return self._managed_accounts

    def _validate_account_scope(self) -> None:
        accounts = set(self.managed_accounts)
        if self.allowed_accounts and not accounts.issubset(self.allowed_accounts):
            unexpected = sorted(accounts - self.allowed_accounts)
            raise IBKRSafetyError(f"unexpected IBKR account(s): {unexpected}")
        if self.account is not None and self.account not in accounts:
            raise IBKRSafetyError(
                f"configured account {self.account!r} not in managed accounts {sorted(accounts)}"
            )
        if self.account is None and len(accounts) == 1:
            self.account = next(iter(accounts))

    # ---------- snapshots ----------

    def refresh_positions(self, *, timeout: float = 10.0) -> dict[str, Position]:
        app = self._require_app()
        self._positions_end.clear()
        with self._lock:
            self._positions = {}
        app.reqPositions()
        if not self._positions_end.wait(timeout):
            raise IBKRConnectionError("timed out waiting for IBKR positions")
        app.cancelPositions()
        return self.positions()

    def refresh_account(self, *, timeout: float = 10.0) -> dict[str, float]:
        app = self._require_app()
        self._account_ready.clear()
        with self._lock:
            self._request_id += 1
            request_id = self._request_id
        group = self.account or "All"
        tags = "NetLiquidation,TotalCashValue,AvailableFunds,BuyingPower"
        app.reqAccountSummary(request_id, group, tags)
        if not self._account_ready.wait(timeout):
            app.cancelAccountSummary(request_id)
            raise IBKRConnectionError("timed out waiting for IBKR account summary")
        app.cancelAccountSummary(request_id)
        with self._lock:
            return dict(self._account_values)

    def position(self, instrument: str) -> Position:
        with self._lock:
            pos = self._positions.get(instrument)
            return replace(pos) if pos else Position(instrument)

    def positions(self) -> dict[str, Position]:
        with self._lock:
            return {instrument: replace(pos) for instrument, pos in self._positions.items()}

    def equity(self) -> float:
        with self._lock:
            value = self._account_values.get("NetLiquidation")
        if value is None:
            raise IBKRConnectionError("NetLiquidation not available; call refresh_account()")
        return value

    def last_price(self, instrument: str) -> float | None:
        with self._lock:
            return self._last_prices.get(instrument)

    def notional_per_unit(self, instrument: str) -> float | None:
        px = self.last_price(instrument)
        if px is None:
            return None
        spec = self.contracts.get(instrument)
        if spec is None:
            return None
        multiplier = float(spec.multiplier) if spec.multiplier else 1.0
        return px * multiplier

    # ---------- engine Broker protocol ----------

    def submit(self, order: OrderIntent, now: datetime) -> str:
        del now  # IBKR timestamps the accepted order/execution stream.
        if self.read_only:
            raise IBKRSafetyError("IBKR adapter is read-only; refusing order submission")
        app = self._require_app()
        if order.instrument not in self.contracts:
            raise IBKRSafetyError(f"no explicit IBKR contract for {order.instrument!r}")
        if order.valid_until is not None:
            raise NotImplementedError("IBKR valid_until/time-in-force translation is not implemented")
        if order.client_order_id:
            with self._lock:
                existing = self._client_order_ids.get(order.client_order_id)
            if existing is not None:
                return existing

        with self._lock:
            if self._next_order_id is None:
                raise IBKRConnectionError("IBKR nextValidId is unavailable")
            order_id = self._next_order_id
            self._next_order_id += 1
            self._order_intents[order_id] = order
            if order.client_order_id:
                self._client_order_ids[order.client_order_id] = str(order_id)

        contract = _to_ib_contract(self.contracts[order.instrument])
        ib_order = _to_ib_order(order, self.account)
        app.placeOrder(order_id, contract, ib_order)
        return str(order_id)

    def on_data_event(self, event: DataEvent) -> list[Fill]:
        if event.instrument is not None:
            px = _event_price(event)
            if px is not None:
                with self._lock:
                    self._last_prices[event.instrument] = px
        return self.poll_fills()

    def poll_fills(self) -> list[Fill]:
        with self._lock:
            fills = list(self._fills)
            self._fills.clear()
        return fills

    # ---------- callback handlers used by the generated EWrapper ----------

    def _on_next_valid_id(self, order_id: int) -> None:
        with self._lock:
            self._next_order_id = max(order_id, self._next_order_id or order_id)
        self._connected.set()

    def _on_managed_accounts(self, accounts_list: str) -> None:
        accounts = tuple(a.strip() for a in accounts_list.split(",") if a.strip())
        with self._lock:
            self._managed_accounts = accounts

    def _on_position(self, account: str, contract: Any, position: Any, avg_cost: float) -> None:
        if self.account is not None and account != self.account:
            return
        instrument = self._instrument_for_contract(contract)
        if instrument is None:
            return
        quantity = float(position)
        multiplier = float(getattr(contract, "multiplier", "") or 1.0)
        average_price = float(avg_cost) / multiplier if multiplier else float(avg_cost)
        with self._lock:
            self._positions[instrument] = Position(
                instrument=instrument,
                quantity=quantity,
                average_price=average_price,
            )

    def _on_position_end(self) -> None:
        self._positions_end.set()

    def _on_account_summary(self, account: str, tag: str, value: str, currency: str) -> None:
        del currency
        if self.account is not None and account != self.account:
            return
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return
        if math.isfinite(numeric):
            with self._lock:
                self._account_values[tag] = numeric

    def _on_account_summary_end(self, req_id: int) -> None:
        del req_id
        self._account_ready.set()

    def _on_exec_details(self, req_id: int, contract: Any, execution: Any) -> None:
        del req_id
        exec_id = str(getattr(execution, "execId", ""))
        if not exec_id:
            return
        with self._lock:
            if exec_id in self._execution_ids:
                return
            self._execution_ids.add(exec_id)
        instrument = self._instrument_for_contract(contract)
        if instrument is None:
            return
        side_text = str(getattr(execution, "side", "")).upper()
        side = Side.BUY if side_text in {"BOT", "BUY"} else Side.SELL
        order_id = int(getattr(execution, "orderId", 0))
        with self._lock:
            intent = self._order_intents.get(order_id)
        timestamp = _parse_ib_time(str(getattr(execution, "time", "")))
        fill = Fill(
            order_id=str(order_id),
            instrument=instrument,
            side=side,
            quantity=float(getattr(execution, "shares", 0.0)),
            price=float(getattr(execution, "price", 0.0)),
            commission=0.0,
            timestamp=timestamp,
            tag=intent.tag if intent is not None else "",
        )
        with self._lock:
            self._fills.append(fill)

    def _instrument_for_contract(self, contract: Any) -> str | None:
        for instrument, spec in self.contracts.items():
            if _contract_matches(spec, contract):
                return instrument
        return None

    def _require_app(self) -> Any:
        if self._app is None or not self.connected:
            raise IBKRConnectionError("IBKR adapter is not connected")
        return self._app


class IBKRMarketDataAdapter:
    """Reserved for the live IBKR market-data stream.

    Execution is intentionally wired first.  Keeping this explicit stub prevents
    accidental use of broker callbacks as strategy data before timestamp/archive
    semantics are specified.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise IBKRNotConfigured("IBKR market-data streaming is not wired yet")


def _build_ib_app(adapter: IBKRBrokerAdapter) -> Any:
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
    except ImportError as exc:
        raise IBKRNotConfigured(
            "IBKR TWS Python API is not installed. Install the official Python client "
            "from the IBKR TWS API download on the execution host."
        ) from exc

    class _IBApp(EWrapper, EClient):
        def __init__(self) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, self)

        def nextValidId(self, orderId: int) -> None:  # noqa: N802 - IBKR callback name
            adapter._on_next_valid_id(orderId)

        def managedAccounts(self, accountsList: str) -> None:  # noqa: N802
            adapter._on_managed_accounts(accountsList)

        def position(self, account: str, contract: Any, position: Any, avgCost: float) -> None:
            adapter._on_position(account, contract, position, avgCost)

        def positionEnd(self) -> None:  # noqa: N802
            adapter._on_position_end()

        def accountSummary(
            self, reqId: int, account: str, tag: str, value: str, currency: str
        ) -> None:  # noqa: N802
            adapter._on_account_summary(account, tag, value, currency)

        def accountSummaryEnd(self, reqId: int) -> None:  # noqa: N802
            adapter._on_account_summary_end(reqId)

        def execDetails(self, reqId: int, contract: Any, execution: Any) -> None:  # noqa: N802
            adapter._on_exec_details(reqId, contract, execution)

        def error(self, reqId: int, errorCode: int, errorString: str, *args: Any) -> None:
            # Connectivity/status messages are intentionally left to host logging for
            # v0.1. Fatal connection detection/reconciliation is the next milestone.
            del reqId, errorCode, errorString, args

    return _IBApp()


def _to_ib_contract(spec: IBKRContractSpec) -> Any:
    try:
        from ibapi.contract import Contract
    except ImportError as exc:
        raise IBKRNotConfigured("official IBKR TWS Python API is not installed") from exc
    contract = Contract()
    contract.symbol = spec.symbol
    contract.secType = spec.sec_type
    contract.exchange = spec.exchange
    contract.currency = spec.currency
    contract.primaryExchange = spec.primary_exchange
    contract.lastTradeDateOrContractMonth = spec.last_trade_date_or_contract_month
    contract.multiplier = spec.multiplier
    contract.localSymbol = spec.local_symbol
    contract.tradingClass = spec.trading_class
    return contract


def _to_ib_order(intent: OrderIntent, account: str | None) -> Any:
    try:
        from ibapi.order import Order
    except ImportError as exc:
        raise IBKRNotConfigured("official IBKR TWS Python API is not installed") from exc
    order = Order()
    order.action = intent.side.value
    order.totalQuantity = intent.quantity
    if intent.order_type is OrderType.MARKET:
        order.orderType = "MKT"
    elif intent.order_type is OrderType.LIMIT:
        order.orderType = "LMT"
        order.lmtPrice = intent.limit_price
    elif intent.order_type is OrderType.STOP:
        order.orderType = "STP"
        order.auxPrice = intent.stop_price
    else:  # pragma: no cover - enum currently exhaustive
        raise ValueError(intent.order_type)
    order.tif = "DAY"
    order.transmit = True
    if account:
        order.account = account
    if intent.client_order_id:
        # orderRef is user-visible and comes back in executions/open orders.
        order.orderRef = intent.client_order_id[:64]
    return order


def _contract_matches(spec: IBKRContractSpec, contract: Any) -> bool:
    if spec.local_symbol:
        return str(getattr(contract, "localSymbol", "")) == spec.local_symbol
    return (
        str(getattr(contract, "symbol", "")) == spec.symbol
        and str(getattr(contract, "secType", "")) == spec.sec_type
        and (
            not spec.last_trade_date_or_contract_month
            or str(getattr(contract, "lastTradeDateOrContractMonth", ""))
            == spec.last_trade_date_or_contract_month
        )
    )


def _event_price(event: DataEvent) -> float | None:
    payload = event.payload
    close = getattr(payload, "close", None)
    if close is not None:
        return float(close)
    bid = getattr(payload, "bid", None)
    ask = getattr(payload, "ask", None)
    if bid is not None and ask is not None:
        return (float(bid) + float(ask)) / 2.0
    return None


def _parse_ib_time(value: str) -> datetime:
    # Typical TWS API execution timestamps are ``YYYYMMDD HH:MM:SS`` and may
    # include a timezone token in newer API versions. Preserve UTC awareness even
    # when no token is supplied; the raw broker timestamp will be archived later.
    parts = value.strip().split()
    if len(parts) >= 2:
        try:
            naive = datetime.strptime(" ".join(parts[:2]), "%Y%m%d %H:%M:%S")
            return naive.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)
