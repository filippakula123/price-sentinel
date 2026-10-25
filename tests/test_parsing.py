import json
from pathlib import Path

import pytest

from price_sentinel.adapters import ADAPTERS, XKomAdapter
from price_sentinel.models import Availability, Product, identical, money
from price_sentinel.transport import ReadError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1 234,56 zł", 123456),
        ("1\u00a0234,56 PLN", 123456),
        ("1\u202f234,565", 123457),
        ("0,005", 1),
        ("2.345", 235),
        (1234, 123400),
    ],
)
def test_money(value, expected):
    assert money(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "1.234,56", "10 x 30 rat", "10/20"])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        money(value)


@pytest.mark.parametrize("adapter", list(ADAPTERS.values()))
def test_synthetic_common_contract(adapter, synthetic):
    product, observation = adapter.parse(synthetic())
    assert product.variant["color"] == "czarny"
    assert observation.price == 123456
    assert observation.availability == Availability.AVAILABLE
    assert observation.shipping is None
    assert observation.store_lowest_30d is None


@pytest.mark.parametrize(
    "html", ["", "<html><broken", '<script type="application/ld+json">{broken</script>']
)
def test_missing_data(html):
    with pytest.raises(ReadError):
        XKomAdapter().parse(html)


def test_ambiguous_and_conditional_prices(synthetic):
    for offers in (
        {"@type": "AggregateOffer", "lowPrice": 100, "highPrice": 200},
        [{"@type": "Offer", "price": 100}, {"@type": "Offer", "price": 200}],
        {"@type": "Offer", "priceCurrency": "PLN"},
        {"@type": "Offer", "price": "0", "priceCurrency": "PLN"},
        {"@type": "Offer", "price": "100", "priceCurrency": "EUR"},
        {
            "@type": "Offer",
            "price": "100",
            "priceCurrency": "PLN",
            "priceSpecification": {"name": "Z kodem / raty"},
        },
    ):
        with pytest.raises(ReadError):
            XKomAdapter().parse(synthetic(offers=offers))
    with pytest.raises(ReadError):
        XKomAdapter().parse(synthetic() + synthetic())


def test_installments_codes_cashback_not_deducted(synthetic):
    html = synthetic() + "<p>Raty 20 x 30 zł, z kodem TANIEJ 100 zł, cashback 50 zł</p>"
    _, observation = XKomAdapter().parse(html)
    assert observation.price == 123456
    assert "bez odliczania" in observation.promotion


def test_unknown_availability(synthetic):
    for value in ("PreOrder", "Unknown", "", "BackOrder"):
        assert XKomAdapter().parse(synthetic(availability=value))[1].availability == "nieznany"


def test_variant_matching_is_conservative():
    a = Product(model="Telefon", ean="123", variant={"color": "czarny", "size": "256"})
    assert identical(a, a)
    assert not identical(a, a.model_copy(update={"variant": {"color": "biały", "size": "256"}}))
    assert not identical(a, a.model_copy(update={"ean": "124"}))
    assert not identical(Product(model="Tak samo"), Product(model="Tak samo"))


def test_real_xkom_fixture():
    path = Path(__file__).parent / "fixtures" / "xkom-1195326-2026-10-25.html"
    product, observation = XKomAdapter().parse(path.read_text(encoding="utf-8"))
    assert product.model == "Sony PlayStation 5 Slim"
    assert product.variant["sku"] == "1195326"
    assert observation.price == 339900
    assert observation.availability == Availability.UNKNOWN


def test_graph(synthetic):
    data = json.loads(synthetic().split(">", 1)[1].split("</script>")[0])
    html = '<script type="application/ld+json">' + json.dumps({"@graph": [data]}) + "</script>"
    assert XKomAdapter().parse(html)[1].price == 123456
