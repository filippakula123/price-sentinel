"""Synthetic observations only; no store or Discord network requests."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from price_sentinel.alerts import deliver, reasons
from price_sentinel.cli import execute, parser
from price_sentinel.models import Availability, Observation, Subscription
from price_sentinel.storage import Database
from price_sentinel.transport import ReadError

URL = "https://www.x-kom.pl/p/synthetic-rule-types.html"
WEBHOOK = "https://discord.com/api/webhooks/123/synthetic_not_a_secret"


@pytest.mark.parametrize("availability", list(Availability))
@pytest.mark.parametrize("price,matched", [(9999, True), (10000, True), (10001, False)])
def test_price_only_threshold_ignores_availability(availability, price, matched):
    rule = Subscription(rule_type="price_below", target=10000)
    assert bool(reasons(rule, None, Observation(price=price, availability=availability))) == matched


@pytest.mark.parametrize("availability", list(Availability))
def test_legacy_default_still_requires_available(availability):
    rule = Subscription.model_validate_json('{"target":10000}')
    assert rule.rule_type == "available_and_price_below"
    assert bool(reasons(rule, None, Observation(price=9000, availability=availability))) == (
        availability == Availability.AVAILABLE
    )


@pytest.mark.parametrize(
    "values",
    [
        {"rule_type": "unknown"},
        {"rule_type": "price_below"},
        {"rule_type": "price_below", "target": 0},
        {"rule_type": "price_below", "target": 10000, "restock": True},
        {"rule_type": "price_below", "target": 10000, "drop_amount": 100},
        {"rule_type": "price_below", "target": 10000, "drop_percent": 10},
    ],
)
def test_invalid_rule_combinations(values):
    with pytest.raises(ValidationError):
        Subscription(**values)


def test_cli_price_only_and_invalid_edit_are_persistent_and_atomic(monitor, db):
    args = parser().parse_args(["add", URL, "--rule-type", "price_below", "--target", "2000"])
    oid = execute(args, db, monitor.settings)["id"]
    before = db.rows("SELECT body FROM subscriptions")[0]["body"]
    assert json.loads(before)["rule_type"] == "price_below"
    invalid = parser().parse_args(["edit", str(oid), "--rule-type", "price_below"])
    with pytest.raises(ValidationError):
        execute(invalid, db, monitor.settings)
    assert db.rows("SELECT body FROM subscriptions")[0]["body"] == before


def test_price_only_delivery_snapshot_and_availability_change_dedup(
    monitor, db, synthetic, tmp_path
):
    oid = monitor.add(URL, Subscription(rule_type="price_below", target=200000, cooldown=0))
    monitor.http.html = synthetic(availability="Unknown")
    assert monitor.check(oid)["availability"] == Availability.UNKNOWN
    pending = db.rows("SELECT * FROM alerts")[0]
    assert pending["state"] == "pending" and pending["attempts"] == 0
    assert pending["sent_at"] is None and len(pending["fingerprint"]) == 64
    assert "tylko cena" in pending["content"] and "Dostępność: nieznany" in pending["content"]
    sent = []
    assert deliver(db, WEBHOOK, lambda *args: sent.append(args))["wysłane"] == 1
    row = db.rows("SELECT * FROM alerts")[0]
    assert row["fingerprint"] == pending["fingerprint"]
    assert row["state"] == "sent" and row["attempts"] == 1 and row["sent_at"]
    assert deliver(db, WEBHOOK, lambda *args: pytest.fail("duplicate"))["wysłane"] == 0
    assert db.rows("SELECT * FROM alerts")[0] == row
    # Same price, different stock: price-only fingerprint must remain unchanged.
    monitor.http.html = synthetic(availability="InStock")
    monitor.check(oid)
    assert db.rows("SELECT * FROM alerts") == [row]
    restored = Database(tmp_path / "price-only-restored.sqlite3")
    try:
        restored.restore(db.export_snapshot())
        assert restored.export_snapshot()["tables"] == db.export_snapshot()["tables"]
        assert deliver(restored, WEBHOOK, lambda *args: pytest.fail("duplicate"))["wysłane"] == 0
    finally:
        restored.close()
    assert len(sent) == 1


def test_legacy_fingerprint_does_not_change_after_rule_type_added(monitor, db):
    rule = Subscription(target=200000, cooldown=0)
    oid = monitor.add(URL, rule)
    current = monitor.check(oid)
    # Reconstruct the previous release's persisted key, excluding the newly added field.
    legacy_body = rule.model_dump(exclude={"rule_type"})
    legacy_key = json.dumps(
        [oid, legacy_body, current["price"], current["availability"], ["cena docelowa"]],
        sort_keys=True,
        ensure_ascii=False,
    )
    expected = hashlib.sha256(legacy_key.encode()).hexdigest()
    assert db.rows("SELECT fingerprint FROM alerts")[0]["fingerprint"] == expected
    # Old persisted subscription and alert survive another check unchanged.
    with db.conn:
        db.conn.execute("UPDATE subscriptions SET body=?", (json.dumps(legacy_body),))
    monitor.check(oid)
    assert len(db.rows("SELECT * FROM alerts")) == 1


def test_price_only_does_not_alert_on_failed_read(monitor, db):
    oid = monitor.add(URL, Subscription(rule_type="price_below", target=200000))
    monitor.http.html = ReadError("http_403")
    assert monitor.check(oid)["status"] == "http_403"
    assert not db.rows("SELECT * FROM alerts")
    assert not db.rows("SELECT * FROM observations")
