import json
from datetime import UTC, datetime, timedelta

import pytest

from price_sentinel.alerts import deliver, reasons, validate_webhook
from price_sentinel.models import Availability, Observation, Subscription
from price_sentinel.storage import Database, process_lock
from price_sentinel.transport import ReadError

URL = "https://www.x-kom.pl/p/synthetic.html"
WEBHOOK = "https://discord.com/api/webhooks/123/synthetic_not_a_secret"


def test_full_slice_restart_and_dedup(monitor, db, tmp_path):
    oid = monitor.add(URL, Subscription(target=200000))
    assert monitor.check(oid)["price"] == 123456
    assert len(db.rows("SELECT * FROM alerts")) == 1
    sent = []
    assert deliver(db, WEBHOOK, lambda url, content: sent.append(content))["wysłane"] == 1
    assert URL in sent[0] and "za mało danych" in sent[0]
    assert monitor.check(oid)["status"] == "ok"
    reopened = Database(tmp_path / "test.sqlite3")
    try:
        assert len(reopened.rows("SELECT * FROM observations")) == 2
        assert deliver(reopened, WEBHOOK, lambda *args: pytest.fail("Duplikat"))["wysłane"] == 0
        assert len(reopened.rows("SELECT * FROM alerts")) == 1
    finally:
        reopened.close()


def test_failure_does_not_replace_observation(monitor, db):
    oid = monitor.add(URL, Subscription())
    monitor.check(oid)
    good = db.offer(oid)["last_success"]
    monitor.http.html = ReadError("http_403")
    assert monitor.check(oid)["status"] == "http_403"
    assert db.offer(oid)["last_success"] == good
    assert len(db.rows("SELECT * FROM observations")) == 1
    assert len(db.rows("SELECT * FROM checks")) == 2


def test_variant_change_rejected(monitor, db, synthetic):
    oid = monitor.add(URL, Subscription())
    monitor.check(oid)
    monitor.http.html = synthetic(color="biały")
    assert monitor.check(oid)["status"] == "zmiana_wariantu_wymaga_weryfikacji"
    assert len(db.rows("SELECT * FROM observations")) == 1


def test_crud_and_manual_group(monitor, db):
    oid = monitor.add(URL, Subscription())
    other = monitor.add(URL + "2", Subscription())
    monitor.edit(oid, Subscription(target=10000))
    assert (
        json.loads(db.rows("SELECT body FROM subscriptions WHERE offer_id=?", (oid,))[0]["body"])[
            "target"
        ]
        == 10000
    )
    monitor.pause(oid, True)
    assert monitor.check(oid)["status"] == "wstrzymana"
    monitor.pause(oid, False)
    monitor.link(oid, other)
    assert db.offer(oid)["product_id"] == db.offer(other)["product_id"]
    monitor.remove(oid)
    with pytest.raises(ValueError):
        db.offer(oid)


def test_alert_rules():
    old = Observation(price=10000, availability=Availability.UNAVAILABLE)
    current = Observation(price=8000, availability=Availability.AVAILABLE)
    rule = Subscription(target=8500, drop_amount=2000, drop_percent=20, restock=True)
    assert len(reasons(rule, old, current)) == 4
    assert not reasons(rule, old, current.model_copy(update={"availability": Availability.UNKNOWN}))
    assert not reasons(
        rule, old, current.model_copy(update={"availability": Availability.UNAVAILABLE})
    )
    assert reasons(rule, None, current) == ["cena docelowa"]
    assert not reasons(
        Subscription(restock=True),
        old.model_copy(update={"availability": Availability.UNKNOWN}),
        current,
    )


def test_cooldown_and_persistent_dedup(monitor, db, synthetic):
    oid = monitor.add(URL, Subscription(target=200000, cooldown=3600))
    monitor.check(oid)
    deliver(db, WEBHOOK, lambda *args: None)
    monitor.http.html = synthetic(price="1200")
    monitor.check(oid)
    assert len(db.rows("SELECT * FROM alerts")) == 1
    with db.conn:
        db.conn.execute(
            "UPDATE alerts SET sent_at=?", ((datetime.now(UTC) - timedelta(hours=2)).isoformat(),)
        )
    monitor.check(oid)
    assert len(db.rows("SELECT * FROM alerts")) == 2


def test_retry_backoff_and_failed_queue(monitor, db):
    monitor.check(monitor.add(URL, Subscription(target=200000)))

    def failed(*args):
        raise ReadError("discord_http_429")

    for i in range(5):
        if i:
            with db.conn:
                db.conn.execute("UPDATE alerts SET next_attempt='2000-01-01'")
        assert deliver(db, WEBHOOK, failed)["błędy"] == 1
        assert deliver(db, WEBHOOK, failed)["błędy"] == 0
    row = db.rows("SELECT * FROM alerts")[0]
    assert row["attempts"] == 5 and row["state"] == "failed"


def test_no_webhook_keeps_queue(monitor, db):
    monitor.check(monitor.add(URL, Subscription(target=200000)))
    assert deliver(db, None)["oczekujące"] == 1
    assert db.rows("SELECT * FROM alerts")[0]["state"] == "pending"


def test_delivery_respects_cooldown_for_preexisting_queue(monitor, db, synthetic):
    oid = monitor.add(URL, Subscription(target=200000, cooldown=3600))
    monitor.check(oid)
    monitor.http.html = synthetic(price="1100")
    monitor.check(oid)
    assert len(db.rows("SELECT * FROM alerts")) == 2
    sent = []
    result = deliver(db, WEBHOOK, lambda *args: sent.append(args))
    assert result["wysłane"] == 1
    assert result["oczekujące"] == 1
    assert len(sent) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.org/api/webhooks/1/token",
        "http://discord.com/a",
        WEBHOOK + "?wait=true",
        "https://discord.com:444/api/webhooks/1/a",
    ],
)
def test_webhook_validation_redacts(url):
    with pytest.raises(ValueError) as exc:
        validate_webhook(url)
    assert url not in str(exc.value)


def test_process_lock(tmp_path):
    path = tmp_path / "state.lock"
    with process_lock(path):
        with pytest.raises(ValueError, match="Inny proces"):
            with process_lock(path):
                pass
    with process_lock(path):
        pass
