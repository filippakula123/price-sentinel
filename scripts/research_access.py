"""Ręczne, ograniczone badanie publicznych źródeł. Bez prywatnych API i spoofingu."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from price_sentinel.config import DEFAULT_HOSTS
from price_sentinel.diagnostics import diagnostic_url
from price_sentinel.models import now
from price_sentinel.transport import ReadError, SafeHTTP, validate_url


def main():
    http = SafeHTTP(DEFAULT_HOSTS, attempts=1)
    results = []
    for host, page in (
        ("www.mediaexpert.pl", "/gaming/playstation-5/konsole-ps5"),
        ("www.euro.com.pl", "/konsole-playstation-5.bhtml"),
    ):
        try:
            robots = http.get(f"https://{host}/robots.txt", robots=False)
        except ReadError as exc:
            results.append(
                {"host": host, "at": now(), "source": "robots.txt", "status": exc.status}
            )
            continue
        sitemaps = [
            line.split(":", 1)[1].strip()
            for line in robots.splitlines()
            if line.lower().startswith("sitemap:")
        ]
        results.append(
            {
                "host": host,
                "at": now(),
                "source": "robots.txt",
                "status": "ok",
                "sha256": hashlib.sha256(robots.encode()).hexdigest(),
                "sitemaps": sitemaps,
            }
        )
        # Wyłącznie sitemap jawnie wskazany przez robots; bez zgadywania ścieżek API.
        for url in [f"https://{host}{page}", *sitemaps[:1]]:
            entry = {"host": host, "url": diagnostic_url(url), "at": now()}
            try:
                validate_url(url, DEFAULT_HOSTS)
                body = http.get(url)
                entry.update(
                    status="ok",
                    bytes=len(body.encode()),
                    sha256=hashlib.sha256(body.encode()).hexdigest(),
                )
                if url in sitemaps:
                    root = ET.fromstring(body)
                    locations = [
                        element.text
                        for element in root.iter()
                        if element.tag.rsplit("}", 1)[-1] == "loc" and element.text
                    ]
                    entry["locations_sample"] = [
                        u for u in locations if urlsplit(u).hostname == host
                    ][:3]
                else:
                    soup = BeautifulSoup(body, "html.parser")
                    entry["json_ld_scripts"] = len(
                        soup.find_all("script", type="application/ld+json")
                    )
                    entry["rss_links"] = [
                        tag.get("href") for tag in soup.find_all("link", type="application/rss+xml")
                    ][:3]
            except (ReadError, ET.ParseError) as exc:
                entry["status"] = exc.status if isinstance(exc, ReadError) else "invalid_xml"
            results.append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
    Path("docs/access-research.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
