import json
from urllib.parse import urlsplit

from pydantic import ValidationError

from .adapters import ADAPTERS
from .alerts import enqueue
from .diagnostics import read_status
from .models import Observation, Product, Subscription, now
from .transport import ReadError, SafeHTTP, validate_url


class Monitor:
    def __init__(self, db, settings, http=None):
        self.db = db
        self.settings = settings
        self.http = http or SafeHTTP(settings.hosts)

    def add(self, url: str, rule: Subscription, name: str = "Produkt oczekujący na odczyt"):
        host = validate_url(url, self.settings.hosts)
        if host not in ADAPTERS:
            raise ValueError("Domena nie ma zaimplementowanego adaptera")
        return self.db.add(Product(model=name), url, rule)

    def edit(self, oid: int, rule: Subscription):
        self.db.offer(oid)
        with self.db.conn:
            self.db.conn.execute(
                "UPDATE subscriptions SET body=? WHERE offer_id=?", (rule.model_dump_json(), oid)
            )

    def pause(self, oid: int, paused: bool):
        self.db.offer(oid)
        with self.db.conn:
            self.db.conn.execute("UPDATE offers SET paused=? WHERE id=?", (int(paused), oid))

    def remove(self, oid: int):
        self.db.offer(oid)
        with self.db.conn:
            self.db.conn.execute("DELETE FROM offers WHERE id=?", (oid,))
            self.db.conn.execute(
                "DELETE FROM products WHERE id NOT IN (SELECT product_id FROM offers)"
            )

    def link(self, oid: int, other: int):
        a, b = self.db.offer(oid), self.db.offer(other)
        # Ręczne powiązanie jest świadomym potwierdzeniem identyczności wariantów.
        body = json.loads(a["body"])
        body["product_id"] = b["product_id"]
        with self.db.conn:
            self.db.conn.execute(
                "UPDATE offers SET product_id=?,body=? WHERE id=?",
                (b["product_id"], json.dumps(body), oid),
            )

    def check(self, oid: int) -> dict:
        offer = self.db.offer(oid)
        if offer["paused"]:
            return {"id": oid, "status": "wstrzymana"}
        try:
            host = validate_url(offer["url"], self.settings.hosts)
            adapter = ADAPTERS.get(host)
            if adapter is None:
                raise ReadError("brak_adaptera")
            product, observation = adapter.parse(self.http.get(offer["url"]))
            previous = self.db.rows(
                "SELECT body FROM observations WHERE offer_id=? ORDER BY id DESC LIMIT 1", (oid,)
            )
            old = Observation.model_validate_json(previous[0]["body"]) if previous else None
            # Zmiana wariantu/identyfikatora pod tym samym URL wymaga interwencji.
            existing = json.loads(offer["body"])
            known = existing.get("observed_product")
            identity = product.model_dump()
            if known and any(
                known.get(k) != identity.get(k) for k in ("ean", "mpn", "variant", "model", "brand")
            ):
                raise ReadError("zmiana_wariantu_wymaga_weryfikacji")
            existing.update(
                observed_product=identity,
                seller=observation.seller,
                condition=observation.condition,
                variant=product.variant,
            )
            rule = Subscription.model_validate_json(
                self.db.rows("SELECT body FROM subscriptions WHERE offer_id=?", (oid,))[0]["body"]
            )
            with self.db.conn:
                self.db.conn.execute(
                    "INSERT INTO observations(offer_id,at,body) VALUES (?,?,?)",
                    (oid, observation.at, observation.model_dump_json()),
                )
                self.db.conn.execute(
                    "UPDATE offers SET status='ok',last_success=?,body=? WHERE id=?",
                    (observation.at, json.dumps(existing), oid),
                )
                # Każda oferta zachowuje własną tożsamość także w grupie ręcznej.
                if not known:
                    group_size = self.db.rows(
                        "SELECT count(*) AS n FROM offers WHERE product_id=?",
                        (offer["product_id"],),
                    )[0]["n"]
                    if group_size == 1:
                        self.db.conn.execute(
                            "UPDATE products SET body=? WHERE id=?",
                            (product.model_dump_json(), offer["product_id"]),
                        )
                self.db.conn.execute(
                    "INSERT INTO checks(offer_id,at,status) VALUES (?,?,'ok')",
                    (oid, observation.at),
                )
                enqueue(self.db, oid, offer["url"], rule, old, observation)
            return {"id": oid, "status": "ok", **observation.model_dump()}
        except (ReadError, ValidationError) as exc:
            status = exc.status if isinstance(exc, ReadError) else "niepoprawne_dane_strukturalne"
            with self.db.conn:
                self.db.conn.execute("UPDATE offers SET status=? WHERE id=?", (status, oid))
                self.db.conn.execute(
                    "INSERT INTO checks(offer_id,at,status) VALUES (?,?,?)", (oid, now(), status)
                )
            return {"id": oid, "status": status}

    def check_all(self):
        return [
            self.check(r["id"])
            for r in self.db.rows("SELECT id FROM offers WHERE paused=0 ORDER BY id")
        ]

    def status(self):
        offers = self.db.rows("SELECT id,url,paused,status,last_success,product_id FROM offers")
        counts = {
            table: self.db.rows(f"SELECT count(*) AS n FROM {table}")[0]["n"]
            for table in ("products", "offers")
        }
        failures = {}
        latest_checks = {}
        for row in self.db.conn.execute(
            "SELECT f.url,c.at,c.status FROM checks c JOIN offers f ON f.id=c.offer_id "
            "ORDER BY c.at DESC,c.id DESC"
        ):
            host = urlsplit(row["url"]).hostname
            if host not in latest_checks:
                latest_checks[host] = {"at": row["at"], "detail": row["status"]}
            if row["status"] != "ok" and host not in failures:
                failures[host] = {"at": row["at"], "detail": row["status"], "źródło": "monitoring"}
            if set(ADAPTERS) <= failures.keys():
                break
        adapters = []
        for host, adapter in ADAPTERS.items():
            diagnostic = self.db.metadata("diagnostic:" + host)
            success = self.db.metadata("diagnostic_success:" + host)
            failure = self.db.metadata("diagnostic_error:" + host)
            if diagnostic:
                if success is None and diagnostic["status"] == "ok":
                    success = diagnostic
                if failure is None and diagnostic["status"] != "ok":
                    failure = diagnostic
            errors = [value for value in (failures.get(host), failure) if value]
            last_success = max(
                (
                    o["last_success"]
                    for o in offers
                    if urlsplit(o["url"]).hostname == host and o["last_success"]
                ),
                default=None,
            )
            support = adapter.support_status
            events = [value for value in (latest_checks.get(host), diagnostic) if value]
            if events:
                latest = max(events, key=lambda value: value["at"])
                if latest is diagnostic:
                    support = diagnostic["adapter_status"]
                else:
                    support = (
                        ("partial" if adapter.verified else "unverified")
                        if (latest["detail"] == "ok")
                        else read_status(latest["detail"])
                    )
            adapters.append(
                {
                    "host": host,
                    "status": support,
                    "zweryfikowany": adapter.verified,
                    "zakres_weryfikacji": adapter.verification_scope,
                    "ostatni_sukces_monitoringu": last_success,
                    "ostatni_sukces": max(
                        filter(None, [last_success, success["at"] if success else None]),
                        default=None,
                    ),
                    "ostatni_błąd": max(errors, key=lambda value: value["at"]) if errors else None,
                    "ostatnia_diagnostyka": diagnostic,
                }
            )
        return {
            "liczba_produktów": counts["products"],
            "liczba_ofert": counts["offers"],
            "oczekujące_webhooki": self.db.rows(
                "SELECT count(*) AS n FROM alerts WHERE state='pending'"
            )[0]["n"],
            "nieudane_webhooki": self.db.rows(
                "SELECT count(*) AS n FROM alerts WHERE state='failed'"
            )[0]["n"],
            "snapshot": self.db.snapshot_status(),
            "oferty": offers,
            "adaptery": adapters,
        }
