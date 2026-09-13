from datetime import datetime, timedelta, timezone

from causaltrader import AuditLog, TargetPosition

UTC = timezone.utc


def test_decision_fingerprint_ignores_audit_wall_clock_timestamp():
    a = AuditLog()
    b = AuditLog()
    action = TargetPosition("SPY", 1.0, tag="same", reason="same decision")

    a.write(datetime(2026, 1, 1, tzinfo=UTC), "strategy_action", action)
    b.write(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=100), "strategy_action", action)

    assert a.decision_fingerprint() == b.decision_fingerprint()
