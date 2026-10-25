"""HTTPS z przypiętym publicznym IP (ochrona także przed DNS rebinding)."""

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit

import httpx
from protego import Protego


class ReadError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def validate_url(url: str, hosts: frozenset[str]) -> str:
    try:
        p = urlsplit(url)
        if (
            p.scheme != "https"
            or len(url) > 1000
            or p.hostname not in hosts
            or p.port not in (None, 443)
            or p.username
            or p.password
            or p.fragment
            or "\\" in url
            or any(ord(c) < 33 for c in url)
        ):
            raise ValueError
        return p.hostname
    except (ValueError, TypeError) as exc:
        raise ReadError("niedozwolony_url") from exc


def public_ip(host: str) -> str:
    try:
        addresses = sorted(
            {r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        )
    except OSError as exc:
        raise ReadError("błąd_dns") from exc
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ReadError("niepubliczny_adres_ip")
    return addresses[0]


class SafeHTTP:
    def __init__(self, hosts: frozenset[str], *, interval: float = 3, max_bytes: int = 4_000_000):
        self.hosts = hosts
        self.interval = interval
        self.max_bytes = max_bytes
        self.last: dict[str, float] = {}
        self.robots: dict[str, Protego] = {}
        self.robots_at: dict[str, float] = {}

    def _request(self, url: str, host: str) -> tuple[int, dict, bytes]:
        ip = public_ip(host)
        pinned = httpx.URL(url).copy_with(host=ip)
        # Zachowujemy SNI/certyfikat oryginalnego hosta przy połączeniu do IP.
        try:
            with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET",
                    pinned,
                    headers={"Host": host, "User-Agent": "PriceSentinel/0.1"},
                    extensions={"sni_hostname": host},
                ) as response:
                    chunks = bytearray()
                    deadline = time.monotonic() + 45
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline:
                            raise ReadError("przekroczony_czas_odpowiedzi")
                        chunks.extend(chunk)
                        if len(chunks) > self.max_bytes:
                            raise ReadError("zbyt_duża_odpowiedź")
                    return response.status_code, dict(response.headers), bytes(chunks)
        except httpx.HTTPError as exc:
            raise ReadError("błąd_sieci") from exc

    def get(self, url: str, *, robots: bool = True) -> str:
        for _ in range(6):
            host = validate_url(url, self.hosts)
            if robots:
                if host not in self.robots or time.monotonic() - self.robots_at[host] > 3600:
                    try:
                        raw = self.get(f"https://{host}/robots.txt", robots=False)
                    except ReadError as exc:
                        raise ReadError("robots_niedostępny:" + exc.status) from exc
                    if "user-agent:" not in raw.lower():
                        raise ReadError("robots_niepoprawny")
                    parser = Protego.parse(raw)
                    self.robots[host] = parser
                    self.robots_at[host] = time.monotonic()
                parser = self.robots[host]
                if not parser.can_fetch(url, "PriceSentinel"):
                    raise ReadError("robots_zabrania")
                delay = parser.crawl_delay("PriceSentinel") or parser.crawl_delay("*") or 0
            else:
                delay = 0
            for attempt in range(3):
                time.sleep(
                    max(0, max(self.interval, delay) - (time.monotonic() - self.last.get(host, 0)))
                )
                self.last[host] = time.monotonic()
                try:
                    status, headers, body = self._request(url, host)
                except ReadError as exc:
                    if exc.status != "błąd_sieci" or attempt == 2:
                        raise
                    time.sleep(2**attempt)
                    continue
                if status in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = headers.get("retry-after", "0")
                    wait = int(retry) if retry.isdigit() else 0
                    if wait > 60:
                        raise ReadError("http_429_odłóż_kontrolę")
                    time.sleep(max(wait, 2**attempt))
                    continue
                break
            if status in (301, 302, 303, 307, 308):
                url = urljoin(url, headers.get("location", ""))
                validate_url(url, self.hosts)
                if not robots and (urlsplit(url).path != "/robots.txt" or urlsplit(url).query):
                    raise ReadError("nieoczekiwany_redirect_robots")
                continue
            if status != 200:
                raise ReadError(f"http_{status}")
            text = body.decode("utf-8", errors="replace")
            if robots and any(
                s in text.lower()
                for s in ("captcha", "cf-chl-", "verify you are human", "access denied")
            ):
                raise ReadError("blokada_antybotowa")
            return text
        raise ReadError("zbyt_wiele_redirectów")
