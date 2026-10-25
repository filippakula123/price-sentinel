import json
import socket

import pytest

from price_sentinel.config import Settings
from price_sentinel.service import Monitor
from price_sentinel.storage import Database


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Testy jednostkowe nie mogą używać sieci")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture
def db(tmp_path):
    value = Database(tmp_path / "test.sqlite3")
    yield value
    value.close()


@pytest.fixture
def synthetic():
    """Dane syntetyczne, niezależne od faktycznej struktury sklepu."""

    def make(price="1 234,56", availability="InStock", **updates):
        data = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Syntetyczny telefon 256GB czarny",
            "gtin13": "1234567890128",
            "sku": "synthetic-black-256",
            "color": "czarny",
            "brand": {"name": "Test"},
            "offers": {
                "@type": "Offer",
                "price": price,
                "priceCurrency": "PLN",
                "availability": "https://schema.org/" + availability,
            },
        }
        data.update(updates)
        return '<script type="application/ld+json">' + json.dumps(data) + "</script>"

    return make


class FakeHTTP:
    def __init__(self, html):
        self.html = html

    def get(self, url):
        if isinstance(self.html, Exception):
            raise self.html
        return self.html


@pytest.fixture
def monitor(db, tmp_path, synthetic):
    return Monitor(db, Settings(db=tmp_path / "test.sqlite3"), FakeHTTP(synthetic()))
