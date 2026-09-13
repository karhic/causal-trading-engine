# Architecture invariants

These are stronger than implementation details. A production strategy should not be promoted if any of them are violated.

1. **One strategy implementation**: backtest, paper and live use the same strategy class and configuration schema.
2. **Information barrier**: strategy data reads go only through `CausalDataStore` and are filtered by `available_at <= now`.
3. **No environment introspection**: strategy context does not expose mode, raw clock, broker or provider client.
4. **Execution barrier**: strategies emit generic actions; only the engine/broker adapter submits exchange orders.
5. **Causal fills**: a strategy cannot use a completed bar to obtain a fill from that same bar in the simulator.
6. **Actual futures contracts**: continuous/root symbols can be data identities but are not silently treated as tradable contracts.
7. **Deterministic replay**: same code/config/data produces the same decision stream.
8. **Future invariance**: appending future data cannot alter decisions before the append boundary.
9. **Raw input retention**: live inputs should be append-archived before/while they are processed so the observed stream can be replayed exactly.
10. **Idempotent submission key**: engine-generated orders receive deterministic client order IDs derived from strategy version + causal origin.
11. **Frozen versions stay frozen**: signal changes create a new strategy version rather than rewriting the history of an existing forward test.
12. **Canonical ledger**: the runtime's durable output is an append-only ledger of manifest, consumed events, strategy actions, orders and fills. Historical replay and live runs produce the same record types.
13. **Analytics are downstream**: CAGR, Sharpe, drawdown, charts and research summaries are not part of strategy execution. They are computed from the canonical ledger by separate tooling.
14. **Replay/live parity is testable**: a recorded live input stream replayed through the same strategy version must reproduce the same economically meaningful strategy actions/orders/fills, modulo explicitly documented venue effects.

## Why the ledger boundary matters

A backtest should not be a special analytics program that happens to contain the strategy. It is simply chronological replay through the production strategy interface.

```text
historical DataEvents -> ReplayEngine -> canonical ledger
live DataEvents       -> LiveEngine   -> canonical ledger
                                      |
                                      +-> downstream analytics
                                      +-> optional independent verifier
```

The strategy is upstream of the ledger. Analytics are downstream of it. No performance statistic is allowed to influence strategy execution or historical chronology.

## What is not yet guaranteed by v0.1

- process-crash atomicity across "broker accepted order" and "local state checkpoint";
- broker position reconciliation after restart;
- exchange-specific margin/liquidation simulation;
- tick/queue-accurate fills;
- point-in-time corporate-action / survivorship normalization;
- source-specific timestamp normalization.

Those should be implemented explicitly as the first real strategies demand them rather than hidden inside strategy code.
