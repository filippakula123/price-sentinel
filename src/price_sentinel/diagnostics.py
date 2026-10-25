"""Diagnoza dostępu, bez tworzenia produktów, ofert, obserwacji ani alertów."""

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import ValidationError

from .adapters import ADAPTERS
from .models import now
from .transport import ReadError, SafeHTTP, validate_url


def read_status(detail: str) -> str:
    if any(
        word in detail for word in ("http_403", "http_429", "blokada_antybotowa", "robots_zabrania")
    ):
        return "blocked"
    if detail == "brak_adaptera" or detail.startswith(
        (
            "brak_",
            "wiele_ofert",
            "warunkowa_",
            "nieobsługiwana_waluta",
            "niepoprawne_dane_strukturalne",
        )
    ):
        return "unsupported"
    return "error"


def diagnostic_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "REDACTED" if parts.query else "", "")
    )


class StoreVerifier:
    def __init__(self, db, settings, http=None):
        self.db = db
        self.settings = settings
        self.http = http or SafeHTTP(settings.hosts, attempts=1)

    def verify(self, url: str, output: Path | None = None) -> dict:
        if output is not None:
            protected = {self.db.path.resolve(), self.db.path.with_suffix(".lock").resolve()}
            if protected.intersection(
                {output.resolve(), output.with_suffix(output.suffix + ".tmp").resolve()}
            ):
                raise ValueError("Plik diagnostyczny nie może nadpisywać bazy ani jej blokady")
        result = {
            "at": now(),
            "url": None,
            "host": None,
            "status": "rejected",
            "adapter_status": "unsupported",
            "detail": "niedozwolony_url",
            "obserwacja_utworzona": False,
            "max_prób_na_url": 1,
        }
        try:
            host = validate_url(url, self.settings.hosts)
        except ReadError:
            pass
        else:
            result.update(host=host, url=diagnostic_url(url))
            adapter = ADAPTERS.get(host)
            result["adapter"] = type(adapter).__name__ if adapter else None
            result["zweryfikowany_zakres"] = adapter.verification_scope if adapter else None
            try:
                if adapter is None:
                    raise ReadError("brak_adaptera")
                product, observation = adapter.parse(self.http.get(url))
                # Cena celowo nie trafia do diagnostyki ani tabel historii.
                result.update(
                    status="ok",
                    detail="jednoznaczny_Product_Offer_PLN",
                    adapter_status="partial" if adapter.verified else "unverified",
                    dostępność=observation.availability.value,
                    identyfikator_obecny=bool(product.ean or product.mpn),
                )
            except (ReadError, ValidationError) as exc:
                detail = (
                    exc.status if isinstance(exc, ReadError) else ("niepoprawne_dane_strukturalne")
                )
                result.update(
                    status=read_status(detail), adapter_status=read_status(detail), detail=detail
                )
        if output is None:
            output = (
                self.db.path.parent
                / "diagnostics"
                / (result["at"].replace(":", "-") + "-" + uuid4().hex[:8] + ".json")
            )
        result["plik_diagnostyczny"] = str(output.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)
        # Lokalne metadane operacyjne; snapshot domeny nie zawiera tych ścieżek.
        if result["host"]:
            with self.db.conn:
                self.db.set_metadata("diagnostic:" + result["host"], result)
                kind = "success" if result["status"] == "ok" else "error"
                self.db.set_metadata("diagnostic_" + kind + ":" + result["host"], result)
        return result
