"""Jawny test ręczny online. Nie jest częścią testów jednostkowych."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from price_sentinel.adapters import ADAPTERS
from price_sentinel.config import DEFAULT_HOSTS
from price_sentinel.models import now
from price_sentinel.transport import ReadError, SafeHTTP


def main():
    http = SafeHTTP(DEFAULT_HOSTS)
    categories = {
        "www.mediaexpert.pl": "https://www.mediaexpert.pl/gaming/playstation-5/konsole-ps5",
        "www.euro.com.pl": "https://www.euro.com.pl/konsole-playstation-5.bhtml",
        "www.x-kom.pl": "https://www.x-kom.pl/",
    }
    results = []
    for host, category in categories.items():
        result = {"host": host, "at": now(), "category": category}
        try:
            html = http.get(category)
            links = []
            for tag in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                from urllib.parse import urljoin

                url = urljoin(category, tag["href"])
                # Odkryte w faktycznym HTML linki, nigdy wymyślane endpointy.
                if (
                    urlsplit(url).hostname == host
                    and any(
                        s in url.lower() for s in ("playstation-5-slim", "playstation-5-digital")
                    )
                    and url != category
                    and "?" not in url
                    and "#" not in url
                ):
                    links.append(url)
            result["discovered_links"] = list(dict.fromkeys(links))[:3]
            if not links:
                result["status"] = "brak_odkrytego_linku_produktu"
            else:
                url = links[0]
                result["product_url"] = url
                product_html = http.get(url)
                product, observation = ADAPTERS[host].parse(product_html)
                result.update(
                    status="parsed_requires_manual_comparison",
                    product=product.model_dump(),
                    observation=observation.model_dump(),
                )
                out = Path("data/live")
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{host}.html").write_text(product_html, encoding="utf-8")
        except ReadError as exc:
            result["status"] = exc.status
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/live-verification.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
