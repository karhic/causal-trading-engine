from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from .adapters.ibkr import (
    IBKRBrokerAdapter,
    IBKRConnectionError,
    IBKRContractSpec,
    IBKRNotConfigured,
    IBKRSafetyError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only connectivity smoke test for IB Gateway/TWS."
    )
    parser.add_argument("--host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("IBKR_PORT", "4002"))
    )
    parser.add_argument(
        "--client-id", type=int, default=int(os.getenv("IBKR_CLIENT_ID", "17"))
    )
    parser.add_argument("--account", default=os.getenv("IBKR_ACCOUNT") or None)
    parser.add_argument(
        "--timeout", type=float, default=float(os.getenv("IBKR_CONNECT_TIMEOUT", "10"))
    )
    return parser


def _build_adapter(args: argparse.Namespace) -> IBKRBrokerAdapter:
    # SPY is only a deterministic contract identity for the smoke test. No market
    # data is requested and read_only=True makes order submission impossible.
    contracts = {
        "SPY": IBKRContractSpec(
            symbol="SPY",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            primary_exchange="ARCA",
        )
    }
    allowed = {args.account} if args.account else None
    return IBKRBrokerAdapter(
        contracts=contracts,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        account=args.account,
        allowed_accounts=allowed,
        read_only=True,
        connect_timeout=args.timeout,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    broker = _build_adapter(args)
    try:
        broker.connect()
        payload = {
            "connected": broker.connected,
            "host": broker.host,
            "port": broker.port,
            "client_id": broker.client_id,
            "mode": "paper" if broker.port == 4002 else "unknown",
            "read_only": broker.read_only,
            "account": broker.account,
            "managed_accounts": list(broker.managed_accounts),
            "net_liquidation": broker.equity(),
            "positions": {
                instrument: asdict(position)
                for instrument, position in broker.positions().items()
            },
            "next_order_id": broker._next_order_id,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (IBKRNotConfigured, IBKRConnectionError, IBKRSafetyError) as exc:
        print(f"IBKR SMOKE FAILED: {exc}", file=sys.stderr)
        return 2
    finally:
        broker.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
