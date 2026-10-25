import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx

from .models import Availability, Observation, Subscription, now
from .transport import ReadError


def pln(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02d} zł"


def reasons(rule: Subscription, old: Observation | None, current: Observation) -> list[str]:
    result = []
    if current.availability != Availability.AVAILABLE:
        return result
    if rule.target is not None and current.price <= rule.target:
        result.append("cena docelowa")
    if old:
        difference = old.price - current.price
        if rule.drop_amount and difference >= rule.drop_amount:
            result.append("spadek kwotowy")
        if rule.drop_percent and difference * 100 >= old.price * rule.drop_percent:
            result.append("spadek procentowy")
        if rule.restock and old.availability == Availability.UNAVAILABLE:
            result.append("powrót dostępności")
    return result


def enqueue(
    db, oid: int, url: str, rule: Subscription, old: Observation | None, current: Observation
):
    matched = reasons(rule, old, current)
    if not matched:
        return
    last = db.rows(
        "SELECT sent_at FROM alerts WHERE offer_id=? AND sent_at IS NOT NULL "
        "ORDER BY sent_at DESC LIMIT 1",
        (oid,),
    )
    if (
        last
        and (
            datetime.fromisoformat(current.at) - datetime.fromisoformat(last[0]["sent_at"])
        ).total_seconds()
        < rule.cooldown
    ):
        return
    # Ten sam stan cenowy nie jest ponownie wysyłany także po restarcie.
    key = json.dumps(
        [oid, rule.model_dump(), current.price, current.availability, matched],
        sort_keys=True,
        ensure_ascii=False,
    )
    fingerprint = hashlib.sha256(key.encode()).hexdigest()
    previous = pln(old.price) if old else "za mało danych"
    difference = pln(abs(current.price - old.price)) if old else "za mało danych"
    content = (
        f"Price Sentinel: {', '.join(matched)}\n{url}\n"
        f"Poprzednia: {previous}; aktualna: {pln(current.price)}; "
        f"różnica: {difference}"
        f"{' (spadek)' if old and current.price < old.price else ''}\n"
        f"Odczyt UTC: {current.at}. Dostawa: "
        f"{pln(current.shipping) if current.shipping is not None else 'nieznana'}.\n"
        f"Warunki promocji: {current.promotion or 'nieustalone; sprawdź ofertę'}. "
    )
    db.conn.execute(
        "INSERT OR IGNORE INTO alerts(offer_id,fingerprint,content,destination,next_attempt) "
        "VALUES (?,?,?,?,?)",
        (oid, fingerprint, content, rule.destination, now()),
    )


def validate_webhook(url: str):
    try:
        p = urlsplit(url)
        valid = (
            p.scheme == "https"
            and p.hostname == "discord.com"
            and p.port in (None, 443)
            and not p.username
            and not p.password
            and not p.query
            and not p.fragment
            and re.fullmatch(r"/api/webhooks/\d+/[A-Za-z0-9_-]+", p.path)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Niepoprawny webhook Discord (szczegóły ukryte)")


def send_webhook(url: str, content: str):
    validate_webhook(url)
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                url, json={"content": content[:1950], "allowed_mentions": {"parse": []}}
            )
        if response.status_code not in (200, 204):
            raise ReadError(f"discord_http_{response.status_code}")
    except httpx.HTTPError as exc:
        raise ReadError("discord_błąd_sieci") from exc


def deliver(db, webhook: str | None, sender=send_webhook) -> dict:
    result = {"wysłane": 0, "błędy": 0, "oczekujące": 0}
    pending = db.rows(
        "SELECT * FROM alerts WHERE state='pending' AND next_attempt<=? ORDER BY id LIMIT 20",
        (now(),),
    )
    if not webhook:
        result["oczekujące"] = len(pending)
        return result
    validate_webhook(webhook)
    for alert in pending:
        rule_rows = db.rows("SELECT body FROM subscriptions WHERE offer_id=?", (alert["offer_id"],))
        rule = Subscription.model_validate_json(rule_rows[0]["body"])
        recent = db.rows(
            "SELECT sent_at FROM alerts WHERE offer_id=? AND sent_at IS NOT NULL "
            "ORDER BY sent_at DESC LIMIT 1",
            (alert["offer_id"],),
        )
        if recent:
            allowed_at = datetime.fromisoformat(recent[0]["sent_at"]) + timedelta(
                seconds=rule.cooldown
            )
            if datetime.now(UTC) < allowed_at:
                with db.conn:
                    db.conn.execute(
                        "UPDATE alerts SET next_attempt=? WHERE id=?",
                        (allowed_at.isoformat(), alert["id"]),
                    )
                result["oczekujące"] += 1
                continue
        try:
            if alert["destination"] != "default":
                raise ReadError("nieobsługiwane_miejsce_powiadomień")
            sender(webhook, alert["content"])
        except ReadError:
            attempts = alert["attempts"] + 1
            retry = datetime.now(UTC) + timedelta(seconds=min(3600, 30 * 2**attempts))
            with db.conn:
                db.conn.execute(
                    "UPDATE alerts SET attempts=?,next_attempt=?,state=? WHERE id=?",
                    (
                        attempts,
                        retry.isoformat(),
                        "failed" if attempts >= 5 else "pending",
                        alert["id"],
                    ),
                )
            result["błędy"] += 1
        else:
            with db.conn:
                db.conn.execute(
                    "UPDATE alerts SET state='sent',sent_at=?,attempts=attempts+1 WHERE id=?",
                    (now(), alert["id"]),
                )
            result["wysłane"] += 1
    return result
