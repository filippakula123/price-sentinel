"""Daily CLI operations and read-only views of the current database."""

import json
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .alerts import deliver, pln, validate_webhook
from .models import Observation, Subscription

WARSAW = ZoneInfo("Europe/Warsaw")


def local_time(value):
    return datetime.fromisoformat(value).astimezone(WARSAW).isoformat() if value else None


def watchlist(db):
    result = []
    for row in db.rows(
        "SELECT f.*,p.body AS product,s.body AS subscription FROM offers f "
        "JOIN products p ON p.id=f.product_id JOIN subscriptions s ON s.offer_id=f.id "
        "ORDER BY f.id"
    ):
        rule = Subscription.model_validate_json(row["subscription"])
        points = db.rows(
            "SELECT body FROM observations WHERE offer_id=? ORDER BY at DESC,id DESC LIMIT 1",
            (row["id"],),
        )
        current = Observation.model_validate_json(points[0]["body"]) if points else None
        # Preserve each offer's identity even for manually grouped products.
        product = json.loads(row["body"]).get("observed_product") or json.loads(row["product"])
        result.append(
            {
                "id": row["id"],
                "product_id": row["product_id"],
                "nazwa": product["model"],
                "sklep": urlsplit(row["url"]).hostname,
                "aktywna": not bool(row["paused"]),
                "cena_grosze": current.price if current else None,
                "cel_grosze": rule.target,
                "różnica_do_celu_grosze": current.price - rule.target
                if current and rule.target is not None
                else None,
                "dostępność": current.availability if current else "nieznany",
                "typ_reguły": rule.rule_type,
                "ostatni_udany_odczyt": local_time(row["last_success"]),
                "status_odczytu": row["status"],
                "czas_ceny": local_time(current.at) if current else None,
            }
        )
    return result


def daily(monitor, webhook):
    # Configuration errors must be caught before any store request or new observation.
    if not webhook:
        raise ValueError("daily wymaga DISCORD_WEBHOOK_URL; bez wysyłki użyj check")
    validate_webhook(webhook)
    db = monitor.db
    before = db.rows("SELECT count(*) AS n FROM alerts")[0]["n"]
    checks = monitor.check_all()
    created = db.rows("SELECT count(*) AS n FROM alerts")[0]["n"] - before
    delivery = deliver(db, webhook)  # Exactly one outbox pass, no reports or extra retries.
    return {
        "kontrole": checks,
        "alerty": delivery,
        "podsumowanie": {
            "sprawdzone_oferty": len(checks),
            "udane_odczyty": sum(r["status"] == "ok" for r in checks),
            "błędy_odczytu": sum(r["status"] != "ok" for r in checks),
            "nowe_alerty": created,
            "wysłane_alerty": delivery["wysłane"],
            "błędy_wysyłki": delivery["błędy"],
            "oczekujące_alerty": db.rows("SELECT count(*) AS n FROM alerts WHERE state='pending'")[
                0
            ]["n"],
        },
    }


def brief_report(monitor):
    rows = watchlist(monitor.db)
    active = [r for r in rows if r["aktywna"]]
    names = list(dict.fromkeys(r["nazwa"] for r in active))
    lines = [
        "Price Sentinel — podsumowanie bieżącej bazy (Europe/Warsaw)",
        f"Aktywne produkty: {len({r['product_id'] for r in active})}; oferty: {len(active)}.",
        "Produkty: " + (", ".join(names[:5]) or "brak") + (" …" if len(names) > 5 else ""),
        "Najbliższe cele (ostatnie zapisane ceny, bez dostawy):",
    ]
    targets = sorted(
        (r for r in active if r["różnica_do_celu_grosze"] is not None),
        key=lambda r: (abs(r["różnica_do_celu_grosze"]), r["id"]),
    )[:5]
    for row in targets:
        delta = row["różnica_do_celu_grosze"]
        direction = (
            "powyżej celu" if delta > 0 else "poniżej celu" if delta < 0 else "cel osiągnięty"
        )
        lines.append(
            f"#{row['id']} {row['nazwa']}: {pln(row['cena_grosze'])}, "
            f"cel {pln(row['cel_grosze'])}; "
            f"{pln(abs(delta))} {direction}; {row['dostępność']}; "
            f"odczyt {row['czas_ceny']}; status {row['status_odczytu']}"
        )
    if not targets:
        lines.append("brak ofert z celem i udanym odczytem")
    lines.append("Ostatnie alerty (do 5, także oferty wstrzymane):")
    alerts = monitor.db.rows(
        "SELECT id,offer_id,state,attempts,sent_at FROM alerts ORDER BY id DESC LIMIT 5"
    )
    for alert in alerts:
        lines.append(
            f"#{alert['id']} oferta #{alert['offer_id']}: {alert['state']}, "
            f"próby {alert['attempts']}, wysłano {local_time(alert['sent_at']) or 'brak'}"
        )
    if not alerts:
        lines.append("brak")
    lines.append("Ostatnie błędy adapterów (także historyczne):")
    errors = [a for a in monitor.status()["adaptery"] if a["ostatni_błąd"]]
    for adapter in errors:
        error = adapter["ostatni_błąd"]
        lines.append(f"{adapter['host']}: {error['detail']} ({local_time(error['at'])})")
    if not errors:
        lines.append("brak zapisanych błędów")
    latest = max(
        (r["ostatni_udany_odczyt"] for r in rows if r["ostatni_udany_odczyt"]),
        key=datetime.fromisoformat,
        default=None,
    )
    lines.append(f"Ostatni udany odczyt: {latest or 'brak'}")
    return "\n".join(lines)
