# causaltrader

A deliberately small **research → backtest → paper → live** trading spine built around one invariant:

> **Strategy code is not allowed to know whether it is backtesting, paper trading, or live trading.**

The strategy sees only a plain current timestamp, point-in-time data, a read-only broker-neutral account view, persistent strategy state and fill events. It emits broker-agnostic targets or orders. Data transport, execution venue, simulation and wall-clock/replay-clock differences live outside the strategy.

This is v0.1: enough structure to start freezing candidate edges and accumulating trustworthy forward records without trying to build QuantConnect.

## Why this exists

Research scripts tend to acquire four dangerous properties:

1. they can accidentally see future information;
2. live code quietly differs from backtest code;
3. vendor-specific calls leak into signal logic;
4. six months later nobody can reconstruct why a trade happened.

`causaltrader` makes those problems architectural rather than matters of discipline.

## Core model

```text
                          SAME STRATEGY
                               │
                               ▼
                      StrategyContext
                    /       |       \
             causal data   now     account
                    \       |       /
                               │
                  TargetWeight / TargetPosition
                         or OrderIntent
                               │
                               ▼
                       ExecutionPlanner
                               │
                               ▼
                             Broker

BACKTEST = ReplayClock + historical DataEvent stream + SimBroker
PAPER    = WallClock   + live DataEvent stream       + paper Broker adapter
LIVE     = WallClock   + live DataEvent stream       + live Broker adapter
```

There is no `ctx.mode`, raw broker, raw provider client, or raw clock in the strategy context, so there is no supported `if backtest:` escape hatch.

## Point-in-time data guarantee

Every observation has two independent timestamps:

```python
DataEvent(
    event_time=...,    # period/instant the observation describes
    available_at=...,  # earliest instant the strategy is allowed to know it
)
```

A July macro observation released on 12 August has a July `event_time` but an August `available_at`. Revisions are separate events with later `available_at` timestamps.

The strategy receives only `CausalDataStore`. It cannot request an `as_of` later than `ctx.now`, and events with `available_at > ctx.now` are invisible even if they are physically present in the store.

```python
latest = ctx.data.latest("macro.cpi", "US")
bars = ctx.data.history("market.bar.1d", "SPY", count=200)
```

Do **not** hand production strategies unrestricted provider clients or full historical DataFrames.

## Causal execution simulation

`SimBroker` deliberately evaluates existing orders **before** the strategy sees a newly completed bar.

If a strategy sees the full OHLC of Monday's daily bar and emits a market order, that order cannot fill on Monday's close/open/high/low. It first becomes eligible on Tuesday's bar and a market order fills at Tuesday's open (plus configured slippage).

Basic MARKET, LIMIT and STOP orders are supported. Bar-based limit/stop logic handles gaps conservatively. Richer quote/order-book fill models can be added behind the same `Broker` interface later.

## Broker-independent actions

Strategies can emit:

```python
TargetWeight("SPY", 1.0)
TargetPosition("ES-202609", 2)
OrderIntent("BTCUSDT", Side.BUY, 0.01, OrderType.STOP, stop_price=...)
```

Use targets when execution is implementation detail. Use explicit `OrderIntent` when entry mechanics are part of the edge.

Futures contract multipliers are respected when translating target portfolio weights to quantities.

## Futures are explicit contracts

Continuous roots are data concepts, not tradable instruments.

```python
chain = FuturesChain("CL", ("CL-202609", "CL-202610", "CL-202611"))
f1 = chain.nth(1)
f2 = chain.nth(2)
```

The commodity example ranks roots using actual F1/F2 histories and emits positions in the actual front contracts.

## Audit log

Every run can write append-only JSONL records:

- run manifest;
- data events;
- strategy actions;
- order submissions;
- fills.

A manifest records strategy name/version, mode, config, data sources and code revision. Add provider dataset versions/checksums as we wire real data archives.

```python
AuditLog("runs/2026-08-11/commodity_basis.jsonl")
```

Strategy-owned JSON state can be made crash-persistent with `JsonState`.

## Repository layout

```text
src/causaltrader/
  models.py       typed events, bars, futures chains, orders, fills
  clock.py        ReplayClock / WallClock
  data.py         causal point-in-time data barrier
  engine.py       shared EngineCore + ReplayEngine + LiveEngine
  broker.py       Broker protocol + causal SimBroker
  portfolio.py    target -> generic order planner
  audit.py        append-only audit log
  state.py        memory / crash-persistent JSON state
  catalog.py      vendor-independent dataset semantics
  adapters/
    ibkr.py       boundary for IBKR data/execution transport
    binance.py    boundary for Binance data/execution transport
examples/
  freeburg_shape.py
  btc_nr7_shape.py
  commodity_basis_shape.py
  run_demo.py
tests/
```

## Run it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
python examples/run_demo.py
```

## Acceptance tests already included

### 1. Point-in-time visibility
A future macro release can physically exist in the store but remains invisible until its `available_at` timestamp.

### 2. Revision safety
A revised macro observation cannot overwrite the value the historical strategy saw before the revision existed.

### 3. Future invariance
Appending future market data cannot alter any prior strategy action/order/fill.

### 4. No same-bar fill leakage
An order emitted after seeing a completed bar first fills on a later bar.

### 5. Determinism
Same strategy + config + data produces the same decision fingerprint.

### 6. Futures identity
The root (`CL`) is explicitly separate from the tradable front contract (`CL-202609`).

## Example strategy shapes

The examples are intentionally **interfaces, not claims about the edge**:

- `freeburg_shape.py`: slow heterogeneous macro/regime data;
- `btc_nr7_shape.py`: intraday bars with execution logic as part of the signal;
- `commodity_basis_shape.py`: cross-sectional F1/F2 futures ranking and rolling actual contracts.

The next job is to port the actual frozen strategy implementations and require them to reproduce their existing reference backtests before promotion.

## Promotion lifecycle

Recommended convention:

```text
RESEARCH -> CANDIDATE -> FROZEN -> PAPER -> LIVE_READY -> LIVE
```

Never mutate a frozen strategy version. Improvements become a new version and both can continue accumulating forward evidence.

## What v0.1 intentionally does NOT do

- no GUI;
- no optimizer;
- no distributed compute;
- no tick-perfect exchange simulator;
- no hard dependency on an IBKR/Binance SDK;
- no universal margin model;
- no attempt to normalize every dataset on earth.

Those are additions only when an actual edge needs them.

## Next implementation milestones

1. Port the real Freeburg strategy and reproduce the existing causal reference result exactly.
2. Wrap the existing Binance paper trader behind `BinanceMarketDataAdapter` / `BinanceBrokerAdapter` and replay a recorded live session byte-for-byte.
3. Wire IBKR paper market data + execution in `adapters/ibkr.py`.
4. Port/freeze the commodity basis strategy, including contract calendar/roll rules and the precise F1/F2 signal definition.
5. Persist every consumed live event into a raw archive and run live-vs-replay parity checks.
6. Add portfolio risk/margin constraints only after the first real strategies require them.

## Design rule

If a strategy can get information by any route other than `ctx.data`, or can place an order anywhere other than the broker abstraction, treat that as a bug.

## Public reusable-library integration

CausalTrader is an independent Python package, not a Freeburg-only module.
Install the library from its GitHub source at an immutable commit, or locally
with `python -m pip install .`. The [Freeburg system](https://github.com/karhic/alpha-strategies)
uses the packaged engine for both archived replay and forward monitoring.

The core contract deliberately separates strategy logic from the clock, causal
data feed and broker simulator. A sample implementation is in `examples/` and
acceptance tests in `tests/`. Version 0.1 is a research-grade implementation;
it is **not** a guarantee of production-execution quality or a certified
live-trading platform. The project is MIT licensed.
