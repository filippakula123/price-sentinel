import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOSTS = frozenset({"www.mediaexpert.pl", "www.euro.com.pl", "www.x-kom.pl"})


@dataclass(frozen=True)
class Settings:
    db: Path = field(
        default_factory=lambda: Path(os.getenv("PRICE_SENTINEL_DB", "data/sentinel.sqlite3"))
    )
    hosts: frozenset[str] = field(
        default_factory=lambda: frozenset(
            os.getenv("PRICE_SENTINEL_HOSTS", ",".join(sorted(DEFAULT_HOSTS))).split(",")
        )
    )
    webhook: str | None = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL"), repr=False
    )
