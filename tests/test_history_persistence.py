import copy
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from price_sentinel.alerts import deliver
from price_sentinel.cli import execute, parser
from price_sentinel.config import Settings
from price_sentinel.discord_bot import authorized
from price_sentinel.history import chart, compare, export_data, history, report
from price_sentinel.models import Subscription
from price_sentinel.storage import Database, save_snapshot

URL = "https://www.x-kom.pl/p/synthetic.html"


def test_snapshot_roundtrip_including_alert_state(monitor, db, tmp_path):
    oid = monitor.add(URL, Subscription(target=200000, restock=True))
    monitor.check(oid)
    monitor.pause(oid, True)
    path = tmp_path / "snapshot.json"
    save_snapshot(db, path)
    target = Database(tmp_path / "restored.sqlite3")
    try:
        target.restore(json.loads(path.read_text(encoding="utf-8")))
        assert target.export_snapshot()["tables"] == db.export_snapshot()["tables"]
        assert target.rows("SELECT * FROM alerts")[0]["state"] == "pending"
        assert target.offer(oid)["paused"] == 1
    finally:
        target.close()


def test_snapshot_cli_integration_repeat_restore_keeps_observations_and_alerts(
    monitor, db, tmp_path
):
    webhook = "https://discord.com/api/webhooks/123/synthetic_secret"
    first = monitor.add(URL, Subscription(target=200000, cooldown=0))
    monitor.check(first)
    deliver(db, webhook, lambda *args: None)
    second = monitor.add(URL + "-pending", Subscription(target=200000))
    monitor.check(second)
    third = monitor.add(URL + "-failed", Subscription(target=200000))
    monitor.check(third)
    with db.conn:
        db.conn.execute("UPDATE alerts SET state='failed',attempts=5 WHERE offer_id=?", (third,))
    snapshot = tmp_path / "snapshot.json"
    execute(parser().parse_args(["snapshot", str(snapshot)]), db, monitor.settings)
    expected = db.export_snapshot()["tables"]
    assert len(expected["observations"]) == 3
    assert {a["state"] for a in expected["alerts"]} == {"sent", "pending", "failed"}
    restored_path = tmp_path / "restored.sqlite3"
    target = Database(restored_path)
    try:
        args = parser().parse_args(["restore", str(snapshot)])
        execute(args, target, monitor.settings)
        execute(args, target, monitor.settings)
        assert target.export_snapshot()["tables"] == expected
        assert len(target.rows("SELECT * FROM observations")) == 3
    finally:
        target.close()
    # Restart procesu/bazy nie otwiera ponownie wysłanych ani failed alertów.
    target = Database(restored_path)
    sent = []
    try:
        assert target.export_snapshot()["tables"] == expected
        assert target.snapshot_status()["status"] == "restored"
        assert deliver(target, webhook, lambda url, text: sent.append(text))["wysłane"] == 1
        assert URL + "-pending" in sent[0]
        assert deliver(target, webhook, lambda *args: pytest.fail("Duplikat"))["wysłane"] == 0
        assert len(target.rows("SELECT * FROM observations")) == 3
        assert len(target.rows("SELECT * FROM alerts WHERE state='failed'")) == 1
    finally:
        target.close()


def test_restore_atomic_on_bad_data(monitor, db):
    monitor.add(URL, Subscription())
    original = db.export_snapshot()
    corrupt = copy.deepcopy(original)
    corrupt["tables"]["offers"][0]["product_id"] = 99999
    with pytest.raises(sqlite3.IntegrityError):
        db.restore(corrupt)
    assert db.export_snapshot()["tables"] == original["tables"]
    corrupt["schema_version"] = 999
    with pytest.raises(ValueError):
        db.restore(corrupt)


def test_empty_history_and_real_minimum(monitor, db, synthetic):
    oid = monitor.add(URL, Subscription())
    assert history(db, oid)["status"] == "za mało danych"
    monitor.check(oid)
    assert history(db, oid)["minima_grosze"]["7"] is None
    monitor.http.html = synthetic(price="1100")
    monitor.check(oid)
    data = history(db, oid)
    assert data["minima_grosze"] == {"7": 110000, "30": 110000, "90": 110000}
    assert all(o["store_lowest_30d"] is None for o in data["obserwacje"])


def test_gaps_and_chart(monitor, db, tmp_path):
    oid = monitor.add(URL, Subscription())
    monitor.check(oid)
    first = (datetime.now(UTC) - timedelta(days=4)).isoformat()
    with db.conn:
        db.conn.execute(
            "UPDATE observations SET at=?, body=json_set(body,'$.at',?)", (first, first)
        )
        db.conn.execute(
            "INSERT INTO checks(offer_id,at,status) VALUES (?,datetime('now'),'http_403')", (oid,)
        )
    monitor.check(oid)
    data = history(db, oid, days=1000)
    assert {g["powód"] for g in data["luki"]} >= {"przerwa_w_monitorowaniu", "http_403"}
    out = tmp_path / "history.png"
    chart(db, oid, out)
    assert out.read_bytes().startswith(b"\x89PNG")


def test_compare_unknown_shipping_not_zero(monitor, db):
    oid = monitor.add(URL, Subscription())
    monitor.check(oid)
    data = compare(db, db.offer(oid)["product_id"])
    assert data[0]["razem_grosze"] is None
    assert data[0]["ostatnia_obserwacja"]["shipping"] is None


def test_exports(monitor, db, tmp_path):
    oid = monitor.add(URL, Subscription())
    monitor.check(oid)
    out = tmp_path / "export.json"
    export_data(db, out, "json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["price"] == 123456
    export_data(db, out, "csv")
    assert "shipping" in out.read_text(encoding="utf-8-sig")
    assert "123456" in out.read_text(encoding="utf-8-sig")


def test_report_dedup_local_calendar(monitor, db, monkeypatch):
    from price_sentinel import history as module

    monitor.check(monitor.add(URL, Subscription()))
    sent = []
    monkeypatch.setattr(module, "send_webhook", lambda url, content: sent.append(content))
    assert "za mało danych" in report(db, "daily", webhook="synthetic")
    report(db, "daily", webhook="synthetic")
    report(db, "weekly", webhook="synthetic")
    assert len(sent) == 2
    assert len(db.rows("SELECT * FROM report_runs")) == 2


def test_warsaw_dst():
    zone = ZoneInfo("Europe/Warsaw")
    assert datetime.fromisoformat("2026-10-25T00:30:00+00:00").astimezone(zone).hour == 2
    assert datetime.fromisoformat("2026-10-25T01:30:00+00:00").astimezone(zone).hour == 2
    assert datetime.fromisoformat("2026-10-25T01:30:00+00:00").astimezone(zone).fold == 1


def test_public_snapshot_explicit_consent(db, tmp_path):
    path = tmp_path / "state.json"
    args = parser().parse_args(["snapshot", str(path), "--public"])
    with pytest.raises(ValueError, match="ack-public-data"):
        execute(args, db, Settings())
    assert not path.exists()


def test_discord_auth():
    assert authorized(1, 2, 1, 2)
    assert not authorized(3, 2, 1, 2)
    assert not authorized(1, 3, 1, 2)
    assert not authorized(1, None, 1, 2)
