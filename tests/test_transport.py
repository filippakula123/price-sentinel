import socket

import httpx
import pytest

from price_sentinel.config import DEFAULT_HOSTS
from price_sentinel.transport import ReadError, SafeHTTP, public_ip, validate_url

URL = "https://www.x-kom.pl/p/synthetic.html"
ROBOTS = (200, {}, b"User-agent: *\nDisallow: /private/*\nDisallow: /*?token=*\n")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.x-kom.pl/a",
        "https://x-kom.pl/a",
        "https://www.x-kom.pl.evil.org/a",
        "https://www.x-kom.pl@evil.org/a",
        "https://evil.org@www.x-kom.pl/a",
        "https://www.x-kom.pl:444/a",
        "https://127.0.0.1/a",
        "https://[::1]/a",
        "https://www.x-kom.pl./a",
        "https://www.x-kom.pl/a#fragment",
        "https://www.x-kom.pl\\@evil.org/a",
        "https://www.x-kom.pl/a\n",
        "https://www.x-kom.pl:abc/a",
        "https://2130706433/a",
    ],
)
def test_bad_urls(url):
    with pytest.raises(ReadError, match="niedozwolony_url"):
        validate_url(url, DEFAULT_HOSTS)


def test_good_url():
    assert validate_url(URL, DEFAULT_HOSTS) == "www.x-kom.pl"


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "0.0.0.0",
    ],
)
def test_private_dns(ip, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0, 0, 0, "", (ip, 443))])
    with pytest.raises(ReadError, match="niepubliczny_adres_ip"):
        public_ip("www.x-kom.pl")


def fake_http(monkeypatch, responses):
    http = SafeHTTP(DEFAULT_HOSTS, interval=0)
    calls = []

    def request(url, host):
        calls.append(url)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(http, "_request", request)
    monkeypatch.setattr("price_sentinel.transport.time.sleep", lambda seconds: None)
    return http, calls


@pytest.mark.parametrize(
    "destination",
    [
        "http://www.x-kom.pl/a",
        "https://127.0.0.1/a",
        "https://evil.org/a",
        "https://www.x-kom.pl:444/a",
    ],
)
def test_redirect_validation(destination, monkeypatch):
    http, calls = fake_http(monkeypatch, [ROBOTS, (302, {"location": destination}, b"")])
    with pytest.raises(ReadError, match="niedozwolony_url"):
        http.get(URL)
    assert len(calls) == 2


def test_redirect_checks_target_robots(monkeypatch):
    http, calls = fake_http(monkeypatch, [ROBOTS, (302, {"location": "/private/product"}, b"")])
    with pytest.raises(ReadError, match="robots_zabrania"):
        http.get(URL)
    assert len(calls) == 2


def test_cross_host_redirect_robots(monkeypatch):
    http, calls = fake_http(
        monkeypatch,
        [
            ROBOTS,
            (302, {"location": "https://www.euro.com.pl/a"}, b""),
            (200, {}, b"User-agent: *\nDisallow: /\n"),
        ],
    )
    with pytest.raises(ReadError, match="robots_zabrania"):
        http.get(URL)
    assert calls[-1] == "https://www.euro.com.pl/robots.txt"


def test_robots_wildcards(monkeypatch):
    http, calls = fake_http(monkeypatch, [ROBOTS])
    with pytest.raises(ReadError, match="robots_zabrania"):
        http.get(URL + "?token=abc")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response,match,count",
    [
        ((403, {}, b""), "http_403", 2),
        ((429, {}, b""), "http_429", 4),
        ((503, {}, b""), "http_503", 4),
        ((200, {}, b"<html>CAPTCHA</html>"), "blokada_antybotowa", 2),
        (ReadError("błąd_sieci"), "błąd_sieci", 4),
    ],
)
def test_errors_bounded_retries(response, match, count, monkeypatch):
    http, calls = fake_http(monkeypatch, [ROBOTS, response, response, response])
    with pytest.raises(ReadError, match=match):
        http.get(URL)
    assert len(calls) == count


def test_unavailable_robots_fail_closed(monkeypatch):
    http, calls = fake_http(monkeypatch, [(404, {}, b"")])
    with pytest.raises(ReadError, match="robots_niedostępny:http_404"):
        http.get(URL)
    assert len(calls) == 1


def test_large_retry_after_is_deferred(monkeypatch):
    http, calls = fake_http(monkeypatch, [ROBOTS, (429, {"retry-after": "600"}, b"")])
    with pytest.raises(ReadError, match="odłóż_kontrolę"):
        http.get(URL)
    assert len(calls) == 2


def test_pinned_ip_sni_and_size_limit(monkeypatch):
    real_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, content=b"1234567890")

    monkeypatch.setattr("price_sentinel.transport.public_ip", lambda host: "93.184.216.34")
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle))
    )
    http = SafeHTTP(DEFAULT_HOSTS, max_bytes=5)
    with pytest.raises(ReadError, match="zbyt_duża_odpowiedź"):
        http._request(URL, "www.x-kom.pl")
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["host"] == "www.x-kom.pl"
    assert requests[0].extensions["sni_hostname"] == "www.x-kom.pl"
