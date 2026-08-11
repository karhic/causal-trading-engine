from datetime import datetime,timezone
from causaltrader import Bar,DataEvent,JsonlEventArchive,OrderIntent,Side,SimBroker
UTC=timezone.utc
def test_event_archive_roundtrips_typed_events(tmp_path):
    event=DataEvent("binance","market.bar.5m","BTCUSDT",datetime(2026,8,11,10,tzinfo=UTC),datetime(2026,8,11,10,5,tzinfo=UTC),Bar(100,105,99,103,42)); archive=JsonlEventArchive(tmp_path/"events.jsonl"); archive.append(event); [restored]=archive.read(); assert restored==event; assert isinstance(restored.payload,Bar)
def test_client_order_id_makes_submission_idempotent():
    broker=SimBroker(); now=datetime(2026,8,11,tzinfo=UTC); order=OrderIntent("X",Side.BUY,1,client_order_id="strategy:v1:event:abc:0"); first=broker.submit(order,now); second=broker.submit(order,now); assert first==second; assert len(broker._pending)==1
