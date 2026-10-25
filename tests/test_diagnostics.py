import json
import logging
import traceback

import httpx
import pytest

from price_sentinel.cli import execute, parser
from price_sentinel.config import Settings
from price_sentinel.diagnostics import StoreVerifier
from price_sentinel.transport import ReadError

WEBHOOK = "https://discord.com/api/webhooks/123456/synthetic_secret_token"


@pytest.mark.parametrize("status", [204, 403, 429])
def test_test_webhook_one_post_redacted(status, monkeypatch, caplog):
    real_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status)

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle))
    )
    caplog.set_level(logging.INFO, logger="httpx")
    args = parser().parse_args(["test-webhook"])
    settings = Settings(webhook=WEBHOOK)
    if status == 204:
        result = execute(args, None, settings)
        assert result["wysłane"] == 1 and "***" in result["webhook"]
    else:
        with pytest.raises(ReadError, match=f"discord_http_{status}"):
            execute(args, None, settings)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    payload = json.loads(requests[0].content)
    assert "test połączenia" in payload["content"]
    assert payload["allowed_mentions"] == {"parse": []}
    assert "synthetic_secret_token" not in caplog.text
    assert "123456" not in caplog.text


def test_test_webhook_missing_secret():
    with pytest.raises(ValueError, match="DISCORD_WEBHOOK_URL"):
        execute(parser().parse_args(["test-webhook"]), None, Settings(webhook=None))


def test_test_webhook_network_failure_redacts_debug_and_traceback(monkeypatch, caplog):
    real_client = httpx.Client
    calls = []

    def handle(request):
        calls.append(request)
        logging.getLogger("httpcore.http11").debug("request failed: %s", WEBHOOK)
        raise httpx.ConnectError("connection failed: " + WEBHOOK, request=request)

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle))
    )
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ReadError, match="discord_błąd_sieci") as exc:
        execute(parser().parse_args(["test-webhook"]), None, Settings(webhook=WEBHOOK))
    assert len(calls) == 1
    assert "synthetic_secret_token" not in caplog.text
    assert "synthetic_secret_token" not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize(
    "failure,expected",
    [
        (None, "ok"),
        ("http_403", "blocked"),
        ("http_429", "blocked"),
        ("robots_zabrania", "blocked"),
        ("brak_poprawnej_ceny", "unsupported"),
        ("błąd_sieci", "error"),
    ],
)
def test_verify_does_not_create_domain_data(failure, expected, db, synthetic, tmp_path):
    class Reader:
        calls = 0

        def get(self, url):
            self.calls += 1
            if failure:
                raise ReadError(failure)
            return synthetic()

    reader = Reader()
    verifier = StoreVerifier(db, Settings(), reader)
    before = db.export_snapshot()["tables"]
    result = verifier.verify(
        "https://www.x-kom.pl/p/synthetic.html?secret=private", tmp_path / "diagnostic.json"
    )
    assert result["status"] == expected
    assert result["obserwacja_utworzona"] is False
    assert reader.calls == 1
    assert db.export_snapshot()["tables"] == before
    saved = (tmp_path / "diagnostic.json").read_text(encoding="utf-8")
    assert "secret=private" not in saved and '"price"' not in saved
    assert db.rows("SELECT value FROM metadata WHERE key='diagnostic:www.x-kom.pl'")


def test_verify_invalid_domain_has_no_fetch(db, tmp_path):
    class Reader:
        def get(self, url):
            pytest.fail("Niedozwolona domena nie może być pobrana")

    result = StoreVerifier(db, Settings(), Reader()).verify(
        "https://127.0.0.1/private?token=secret", tmp_path / "rejected.json"
    )
    assert result["status"] == "rejected" and result["url"] is None
    assert not db.rows("SELECT * FROM observations")


def test_verify_uses_single_attempt(db):
    assert StoreVerifier(db, Settings()).http.attempts == 1


def test_diagnostic_cannot_overwrite_database(db, synthetic):
    class Reader:
        def get(self, url):
            pytest.fail("Nie pobieraj strony, gdy cel zapisu jest niepoprawny")

    verifier = StoreVerifier(db, Settings(), Reader())
    with pytest.raises(ValueError, match="nadpisywać bazy"):
        verifier.verify("https://www.x-kom.pl/p/synthetic.html", db.path)
    assert db.rows("SELECT * FROM observations") == []


@pytest.mark.parametrize("failure", ["http_429", "błąd_sieci"])
def test_single_attempt_transport_no_retry(failure, monkeypatch):
    from price_sentinel.config import DEFAULT_HOSTS
    from price_sentinel.transport import SafeHTTP

    http = SafeHTTP(DEFAULT_HOSTS, attempts=1, interval=0)
    calls = []

    def request(url, host):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return 200, {}, b"User-agent: *\nAllow: /"
        if failure == "błąd_sieci":
            raise ReadError(failure)
        return 429, {}, b""

    monkeypatch.setattr(http, "_request", request)
    with pytest.raises(ReadError, match=failure):
        http.get("https://www.x-kom.pl/p/synthetic.html")
    assert len(calls) == 2  # robots + dokładnie jedna próba produktu.
