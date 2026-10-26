"""Offline daily operations, using synthetic HTML and mocked Discord delivery only."""

import json

import pytest

from price_sentinel import cli, routine
from price_sentinel.alerts import deliver as real_deliver
from price_sentinel.config import Settings
from price_sentinel.models import Subscription
from price_sentinel.transport import ReadError

URL = "https://www.x-kom.pl/p/synthetic-daily.html"
WEBHOOK = "https://discord.com/api/webhooks/123/synthetic_not_a_secret"


@pytest.fixture
def deliveries(monkeypatch):
    calls, sent = [], []

    def deliver(db, webhook):
        calls.append(webhook)
        return real_deliver(db, webhook, lambda *args: sent.append(args))

    monkeypatch.setattr(routine, "deliver", deliver)
    return calls, sent


def test_daily_checks_only_active_and_delivers_once_without_duplicate(monitor, db, deliveries):
    active = monitor.add(URL, Subscription(rule_type="price_below", target=200000, cooldown=0))
    paused = monitor.add(URL + "-paused", Subscription(target=200000))
    monitor.pause(paused, True)
    first = routine.daily(monitor, WEBHOOK)
    row = db.rows("SELECT * FROM alerts")[0]
    assert first["podsumowanie"] == {
        "sprawdzone_oferty": 1,
        "udane_odczyty": 1,
        "błędy_odczytu": 0,
        "nowe_alerty": 1,
        "wysłane_alerty": 1,
        "błędy_wysyłki": 0,
        "oczekujące_alerty": 0,
    }
    assert first["kontrole"][0]["id"] == active
    assert row["state"] == "sent" and row["attempts"] == 1 and row["sent_at"]
    second = routine.daily(monitor, WEBHOOK)
    assert second["podsumowanie"]["nowe_alerty"] == 0
    assert second["podsumowanie"]["wysłane_alerty"] == 0
    assert db.rows("SELECT * FROM alerts") == [row]
    assert len(db.rows("SELECT * FROM observations")) == 2
    assert not db.rows("SELECT * FROM checks WHERE offer_id=?", (paused,))
    assert deliveries[0] == [WEBHOOK, WEBHOOK] and len(deliveries[1]) == 1


@pytest.mark.parametrize("webhook", [None, "https://invalid.example/webhook"])
def test_daily_rejects_bad_configuration_before_read(monitor, db, webhook, deliveries):
    monitor.add(URL, Subscription(target=200000))
    before = db.export_snapshot()["tables"]
    with pytest.raises(ValueError):
        routine.daily(monitor, webhook)
    assert db.export_snapshot()["tables"] == before
    assert deliveries == ([], [])


def test_daily_empty_database_still_one_outbox_pass(monitor, deliveries):
    result = routine.daily(monitor, WEBHOOK)
    assert result["podsumowanie"]["sprawdzone_oferty"] == 0
    assert result["alerty"]["wysłane"] == 0
    assert deliveries[0] == [WEBHOOK]


def test_daily_failed_read_does_not_block_other_offers_or_delivery(monitor, db, deliveries):
    first = monitor.add(URL, Subscription(target=200000))
    second = monitor.add(URL + "-second", Subscription(target=200000))
    original_get = monitor.http.get

    def get(url):
        if url == URL:
            raise ReadError("http_403")
        return original_get(url)

    monitor.http.get = get
    result = routine.daily(monitor, WEBHOOK)
    assert [r["status"] for r in result["kontrole"]] == ["http_403", "ok"]
    assert result["podsumowanie"]["błędy_odczytu"] == 1
    assert result["alerty"]["wysłane"] == 1
    assert not db.rows("SELECT * FROM observations WHERE offer_id=?", (first,))
    assert db.rows("SELECT * FROM alerts")[0]["offer_id"] == second


def test_daily_delivery_failure_is_not_retried_in_same_run(monitor, db, monkeypatch):
    monitor.add(URL, Subscription(target=200000))
    calls = []

    def failed(*args):
        calls.append(args)
        raise ReadError("discord_http_429")

    monkeypatch.setattr(routine, "deliver", lambda db, webhook: real_deliver(db, webhook, failed))
    result = routine.daily(monitor, WEBHOOK)
    assert result["podsumowanie"]["błędy_wysyłki"] == 1
    assert result["podsumowanie"]["oczekujące_alerty"] == 1
    assert len(calls) == 1
    assert db.rows("SELECT * FROM alerts")[0]["attempts"] == 1


def test_watchlist_reports_last_known_price_unknowns_and_pause_without_writes(monitor, db):
    oid = monitor.add(URL, Subscription(rule_type="price_below", target=100000))
    unchecked = monitor.add(URL + "-unchecked", Subscription())
    monitor.check(oid)  # FakeHTTP, synthetic HTML; never a network check.
    monitor.http.html = ReadError("http_403")
    monitor.check(oid)
    monitor.pause(oid, True)
    before = db.export_snapshot()["tables"]
    rows = routine.watchlist(db)
    assert rows[0]["nazwa"] == "Syntetyczny telefon 256GB czarny"
    assert rows[0]["sklep"] == "www.x-kom.pl"
    assert rows[0]["cena_grosze"] == 123456
    assert rows[0]["cel_grosze"] == 100000
    assert rows[0]["różnica_do_celu_grosze"] == 23456
    assert rows[0]["typ_reguły"] == "price_below"
    assert rows[0]["dostępność"] == "dostępny"
    assert rows[0]["status_odczytu"] == "http_403" and not rows[0]["aktywna"]
    assert rows[0]["ostatni_udany_odczyt"] == rows[0]["czas_ceny"]
    assert rows[1]["id"] == unchecked and rows[1]["cena_grosze"] is None
    assert rows[1]["różnica_do_celu_grosze"] is None and rows[1]["ostatni_udany_odczyt"] is None
    assert db.export_snapshot()["tables"] == before


def test_watchlist_negative_distance_and_legacy_type(monitor, db):
    oid = monitor.add(URL, Subscription(target=200000))
    monitor.check(oid)
    with db.conn:
        db.conn.execute("UPDATE subscriptions SET body=?", (json.dumps({"target": 200000}),))
    row = routine.watchlist(db)[0]
    assert row["różnica_do_celu_grosze"] == -76544
    assert row["typ_reguły"] == "available_and_price_below"


def test_brief_report_empty_and_readonly(monitor, db):
    before = db.export_snapshot()["tables"]
    text = routine.brief_report(monitor)
    assert "Aktywne produkty: 0; oferty: 0" in text
    assert "Ostatni udany odczyt: brak" in text
    assert "brak zapisanych błędów" in text
    assert db.export_snapshot()["tables"] == before


def test_brief_report_targets_alerts_errors_and_paused_offers(monitor, db, deliveries):
    far = monitor.add(URL, Subscription(target=100000))
    close = monitor.add(URL + "-close", Subscription(target=123000))
    paused = monitor.add(URL + "-paused", Subscription(target=123456))
    routine.daily(monitor, WEBHOOK)
    monitor.pause(paused, True)
    monitor.http.html = ReadError("http_403")
    monitor.check(far)
    before = db.export_snapshot()["tables"]
    text = routine.brief_report(monitor)
    assert "Aktywne produkty: 2; oferty: 2" in text
    target_text = text.split("Ostatnie alerty")[0]
    assert target_text.index(f"#{close} ") < target_text.index(f"#{far} ")
    assert f"#{paused} " not in target_text
    assert "sent, próby 1" in text and "www.x-kom.pl: http_403" in text
    assert "ostatnie zapisane ceny" in text and "status http_403" in text
    assert db.export_snapshot()["tables"] == before


@pytest.mark.parametrize("failed", [False, True])
def test_daily_cli_summary_and_exit_code(monitor, db, deliveries, monkeypatch, capsys, failed):
    monitor.add(URL, Subscription(target=200000))
    if failed:
        monitor.http.html = ReadError("http_403")
    monkeypatch.setattr(cli, "Monitor", lambda *args: monitor)
    monkeypatch.setattr(cli, "Settings", lambda: Settings(db=db.path, webhook=WEBHOOK))
    monkeypatch.setattr("sys.argv", ["price-sentinel", "daily"])
    assert cli.main() == int(failed)
    assert json.loads(capsys.readouterr().out)["podsumowanie"]["błędy_odczytu"] == int(failed)


def test_new_cli_views_and_existing_period_reports(monitor, db, monkeypatch):
    monkeypatch.setattr(cli, "Monitor", lambda *args: monitor)
    settings = Settings(webhook=None)
    result = cli.execute(cli.parser().parse_args(["watchlist"]), db, settings)
    assert result["oferty"] == [] and result["strefa_czasowa"] == "Europe/Warsaw"
    assert "podsumowanie bieżącej bazy" in cli.execute(
        cli.parser().parse_args(["report"]), db, settings
    )
    for period in ("daily", "weekly"):
        text = cli.execute(cli.parser().parse_args(["report", period]), db, settings)
        assert "raport" in text and "Ruchome ostatnie" in text
    with pytest.raises(ValueError, match="wymaga okresu"):
        cli.execute(cli.parser().parse_args(["report", "--notify"]), db, settings)
