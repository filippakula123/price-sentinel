"""Brak zgadywanych selektorów: wyłącznie jednoznaczny Product/Offer JSON-LD."""

import json
from typing import Protocol

from bs4 import BeautifulSoup

from .models import Availability, Observation, Product, money
from .transport import ReadError


class Adapter(Protocol):
    host: str
    verified: bool
    verification_scope: str

    def parse(self, html: str) -> tuple[Product, Observation]: ...


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from nodes(value["@graph"])


class StructuredAdapter:
    verified = False
    verification_scope = "Niezweryfikowany na rzeczywistym produkcie; tylko testy syntetyczne"

    def parse(self, html: str) -> tuple[Product, Observation]:
        soup = BeautifulSoup(html, "html.parser")
        products = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
            except (ValueError, TypeError, RecursionError):
                continue
            for item in nodes(data):
                kind = item.get("@type", [])
                if kind == "Product" or isinstance(kind, list) and "Product" in kind:
                    products.append(item)
        if len(products) != 1:
            raise ReadError("brak_jednoznacznego_produktu")
        p = products[0]
        offers = p.get("offers")
        if isinstance(offers, list):
            if len(offers) != 1:
                raise ReadError("wiele_ofert_wymaga_wyboru")
            offers = offers[0]
        if not isinstance(offers, dict) or offers.get("@type") != "Offer":
            raise ReadError("brak_jednoznacznej_ceny")
        if offers.get("priceCurrency") != "PLN":
            raise ReadError("nieobsługiwana_waluta")
        if not p.get("name"):
            raise ReadError("brak_nazwy")
        # Nie interpretujemy priceSpecification: raty, członkostwo i kody są niejednoznaczne.
        if offers.get("priceSpecification"):
            raise ReadError("warunkowa_lub_niejednoznaczna_cena")
        try:
            price = money(offers["price"])
        except (KeyError, ValueError) as exc:
            raise ReadError("brak_poprawnej_ceny") from exc
        availability = str(offers.get("availability", "")).rsplit("/", 1)[-1]
        state = {
            "InStock": Availability.AVAILABLE,
            "OutOfStock": Availability.UNAVAILABLE,
            "SoldOut": Availability.UNAVAILABLE,
        }.get(availability, Availability.UNKNOWN)
        page_text = soup.get_text(" ", strip=True).lower()
        promotion = None
        if any(word in page_text for word in ("cashback", "kod rabatowy", "z kodem")):
            promotion = "Wzmianka o kodzie/cashback na stronie; bez odliczania od ceny JSON-LD"
        brand = p.get("brand")
        seller = offers.get("seller")
        return Product(
            model=p["name"],
            brand=brand.get("name") if isinstance(brand, dict) else brand,
            ean=p.get("gtin13") or p.get("gtin"),
            mpn=p.get("mpn"),
            variant={k: str(p[k]) for k in ("color", "size", "model", "sku") if p.get(k)},
        ), Observation(
            price=price,
            availability=state,
            seller=seller.get("name") if isinstance(seller, dict) else seller,
            condition=str(offers.get("itemCondition", "nieznany")),
            promotion=promotion,
        )


class MediaExpertAdapter(StructuredAdapter):
    host = "www.mediaexpert.pl"


class EuroAdapter(StructuredAdapter):
    host = "www.euro.com.pl"


class XKomAdapter(StructuredAdapter):
    host = "www.x-kom.pl"
    verified = True  # Cena jednego produktu; zakres: docs/VERIFICATION.md.
    verification_scope = "Cena JSON-LD karty 1195326 (2026-10-25); dostępność nieznana"


ADAPTERS = {a.host: a for a in (MediaExpertAdapter(), EuroAdapter(), XKomAdapter())}
