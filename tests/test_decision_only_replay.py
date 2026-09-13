from datetime import datetime, timezone

from causaltrader import DataEvent, DecisionOnlyPlanner, ReplayEngine, SimBroker, Strategy, TargetWeight

UTC = timezone.utc


class OneDecision(Strategy):
    name = "one-decision"
    version = "1"

    def on_event(self, ctx, event):
        return (TargetWeight("SPY", 1.0, tag="test"),)


def test_decision_only_replay_logs_action_without_requiring_market_price():
    t = datetime(2026, 1, 2, tzinfo=UTC)
    event = DataEvent("test", "clock.weekly", None, t, t, None)
    audit = ReplayEngine(
        strategy=OneDecision(),
        broker=SimBroker(),
        events=[event],
        planner=DecisionOnlyPlanner(),
    ).run()

    assert [r.kind for r in audit.records].count("strategy_action") == 1
    assert [r.kind for r in audit.records].count("order_submitted") == 0
