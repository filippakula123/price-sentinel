from price_sentinel.diagnostics import StoreVerifier
from price_sentinel.models import Subscription
from price_sentinel.storage import save_snapshot
from price_sentinel.transport import ReadError

URL = "https://www.x-kom.pl/p/synthetic.html"


def test_status_counts_last_success_and_failures(monitor, db, tmp_path):
    oid = monitor.add(URL, Subscription(target=200000))
    monitor.check(oid)
    successful_at = db.offer(oid)["last_success"]
    monitor.http.html = ReadError("http_403")
    monitor.check(oid)
    status = monitor.status()
    assert status["liczba_produktów"] == 1
    assert status["liczba_ofert"] == 1
    assert status["oczekujące_webhooki"] == 1
    adapter = next(a for a in status["adaptery"] if a["host"] == "www.x-kom.pl")
    assert adapter["ostatni_sukces"] == successful_at
    assert adapter["ostatni_błąd"]["detail"] == "http_403"
    assert adapter["status"] == "blocked"
    assert status["snapshot"]["status"] == "not_created"


def test_snapshot_status_current_stale_changed_missing(monitor, db, tmp_path):
    oid = monitor.add(URL, Subscription())
    path = tmp_path / "snapshot.json"
    save_snapshot(db, path)
    assert monitor.status()["snapshot"]["status"] == "ok"
    monitor.check(oid)
    assert monitor.status()["snapshot"]["status"] == "stale"
    save_snapshot(db, path)
    path.write_text("corrupt", encoding="utf-8")
    assert monitor.status()["snapshot"]["status"] == "file_changed"
    path.unlink()
    assert monitor.status()["snapshot"]["status"] == "file_missing"


def test_status_reads_latest_diagnostic_without_derived_metadata(monitor, db):
    with db.conn:
        db.set_metadata(
            "diagnostic:www.x-kom.pl",
            {
                "at": "2026-10-25T19:40:00+00:00",
                "status": "ok",
                "adapter_status": "partial",
                "detail": "jednoznaczny_Product_Offer_PLN",
            },
        )
        db.set_metadata(
            "diagnostic:www.euro.com.pl",
            {
                "at": "2026-10-25T19:39:00+00:00",
                "status": "blocked",
                "adapter_status": "blocked",
                "detail": "http_403",
            },
        )
    adapters = {a["host"]: a for a in monitor.status()["adaptery"]}
    assert adapters["www.x-kom.pl"]["ostatni_sukces"] == "2026-10-25T19:40:00+00:00"
    assert adapters["www.euro.com.pl"]["ostatni_błąd"]["detail"] == "http_403"


def test_diagnostic_status_keeps_last_success_and_latest_error(monitor, db, synthetic, tmp_path):
    class Reader:
        failure = False

        def get(self, url):
            if self.failure:
                raise ReadError("http_403")
            return synthetic()

    reader = Reader()
    verifier = StoreVerifier(db, monitor.settings, reader)
    first = verifier.verify(URL, tmp_path / "success.json")
    reader.failure = True
    verifier.verify(URL, tmp_path / "failure.json")
    status = next(a for a in monitor.status()["adaptery"] if a["host"] == "www.x-kom.pl")
    assert status["ostatni_sukces"] == first["at"]
    assert status["ostatni_błąd"]["detail"] == "http_403"
    assert status["status"] == "blocked"
    # Nowszy poprawny monitoring nie może być przesłonięty dawną diagnozą blokady.
    monitor.check(monitor.add(URL, Subscription()))
    status = next(a for a in monitor.status()["adaptery"] if a["host"] == "www.x-kom.pl")
    assert status["status"] == "partial"
    assert status["ostatni_błąd"]["detail"] == "http_403"
