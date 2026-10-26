import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def now() -> str:
    return datetime.now(UTC).isoformat()


def money(value: str | int | float | Decimal) -> int:
    """Złote -> grosze. Żadnych obliczeń finansowych na float."""
    text = re.sub(r"(?:PLN|zł)|[\s\u00a0\u202f]", "", str(value)).replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ValueError("Niepoprawna pojedyncza cena")
    try:
        result = Decimal(text)
        if not result.is_finite() or result <= 0:
            raise ValueError("Cena musi być dodatnia")
        return int((result * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError("Niepoprawna cena") from exc


class Availability(StrEnum):
    AVAILABLE = "dostępny"
    UNAVAILABLE = "niedostępny"
    UNKNOWN = "nieznany"


class Product(BaseModel):
    model: str
    brand: str | None = None
    ean: str | None = None
    mpn: str | None = None
    variant: dict[str, str] = Field(default_factory=dict)


class Offer(BaseModel):
    url: str
    product_id: int
    seller: str | None = None
    condition: str = "nieznany"
    variant: dict[str, str] = Field(default_factory=dict)


class Observation(BaseModel):
    at: str = Field(default_factory=now)
    price: int = Field(gt=0)
    currency: Literal["PLN"] = "PLN"
    availability: Availability = Availability.UNKNOWN
    shipping: int | None = Field(default=None, ge=0)
    promotion: str | None = None
    store_lowest_30d: int | None = Field(default=None, gt=0)
    seller: str | None = None
    condition: str = "nieznany"

    @field_validator("at")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("Czas obserwacji musi mieć strefę czasową")
        return parsed.astimezone(UTC).isoformat()


class Subscription(BaseModel):
    rule_type: Literal["price_below", "available_and_price_below"] = "available_and_price_below"
    target: int | None = Field(default=None, gt=0)
    drop_amount: int | None = Field(default=None, gt=0)
    drop_percent: int | None = Field(default=None, gt=0, le=100)
    restock: bool = False
    cooldown: int = Field(default=21600, ge=0)
    destination: str = "default"

    @model_validator(mode="after")
    def validate_price_only(self):
        if self.rule_type == "price_below":
            if self.target is None:
                raise ValueError("price_below wymaga progu target")
            if self.drop_amount is not None or self.drop_percent is not None or self.restock:
                raise ValueError("price_below obsługuje wyłącznie target, bez drop/percent/restock")
        return self


def identical(a: Product, b: Product) -> bool:
    return bool(
        (
            (a.ean and a.ean == b.ean)
            or (a.mpn and a.brand and a.mpn == b.mpn and a.brand == b.brand)
        )
        and a.variant == b.variant
    )
