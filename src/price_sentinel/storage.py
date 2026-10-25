import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import Offer, Product, Subscription, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offers (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 url TEXT UNIQUE NOT NULL, body TEXT NOT NULL, paused INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'jeszcze_nie_sprawdzono', last_success TEXT);
CREATE TABLE IF NOT EXISTS subscriptions (
 offer_id INTEGER PRIMARY KEY REFERENCES offers(id) ON DELETE CASCADE, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
 at TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS observations_offer ON observations(offer_id, at);
CREATE TABLE IF NOT EXISTS checks (
 id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
 at TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
 fingerprint TEXT UNIQUE NOT NULL, content TEXT NOT NULL, destination TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt TEXT NOT NULL, sent_at TEXT);
CREATE TABLE IF NOT EXISTS report_runs (key TEXT PRIMARY KEY, at TEXT NOT NULL);
"""
TABLES = ("products", "offers", "subscriptions", "observations", "checks", "alerts", "report_runs")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bot serializuje wszystkie operacje blokadą asyncio, także w workerze HTTP.
        self.conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def add(self, product: Product, url: str, rule: Subscription) -> int:
        with self.conn:
            pid = self.conn.execute(
                "INSERT INTO products(body) VALUES (?)", (product.model_dump_json(),)
            ).lastrowid
            offer = Offer(url=url, product_id=pid)
            oid = self.conn.execute(
                "INSERT INTO offers(product_id,url,body) VALUES (?,?,?)",
                (pid, url, offer.model_dump_json()),
            ).lastrowid
            self.conn.execute(
                "INSERT INTO subscriptions VALUES (?,?)", (oid, rule.model_dump_json())
            )
        return oid

    def offer(self, oid: int) -> dict:
        rows = self.rows("SELECT * FROM offers WHERE id=?", (oid,))
        if not rows:
            raise ValueError("Nie ma takiej oferty")
        return rows[0]

    def export_snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "created_at": now(),
            "tables": {table: self.rows(f"SELECT * FROM {table}") for table in TABLES},
        }

    def restore(self, snapshot: dict):
        if snapshot.get("schema_version") != 1 or set(snapshot["tables"]) != set(TABLES):
            raise ValueError("Nieobsługiwany format snapshotu")
        with self.conn:
            for table in reversed(TABLES):
                self.conn.execute(f"DELETE FROM {table}")
            for table in TABLES:
                columns = [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")]
                for row in snapshot["tables"][table]:
                    if set(row) != set(columns):
                        raise ValueError("Niepoprawne kolumny snapshotu")
                    marks = ",".join("?" for _ in columns)
                    self.conn.execute(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})",
                        tuple(row[c] for c in columns),
                    )


@contextmanager
def process_lock(path: Path):
    """OS zwalnia blokadę po awarii; plik zostaje, lecz nie blokuje restartu."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Inny proces używa tej bazy; zakończ go przed uruchomieniem") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save_snapshot(db: Database, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(db.export_snapshot(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
