import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .alerts import deliver, test_webhook
from .config import Settings
from .diagnostics import StoreVerifier
from .history import chart, compare, export_data, history, report
from .models import Subscription, money
from .routine import brief_report, daily, watchlist
from .service import Monitor
from .storage import Database, process_lock, save_snapshot
from .transport import ReadError


def product_url_argument(value: str) -> str:
    if len(value) >= 2 and value.startswith("'") and value.endswith("'"):
        raise argparse.ArgumentTypeError(
            "URL zawiera dosłowne apostrofy. W CMD użyj podwójnych cudzysłowów: "
            '--url "https://www.x-kom.pl/..."'
        )
    return value


def parser():
    p = argparse.ArgumentParser(description="Price Sentinel — monitor cen (bez strony WWW)")
    p.add_argument("--db", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("add", "edit"):
        cmd = sub.add_parser(name)
        cmd.add_argument(
            "url" if name == "add" else "id", type=product_url_argument if name == "add" else int
        )
        cmd.add_argument("--target", type=money)
        cmd.add_argument(
            "--rule-type",
            choices=("price_below", "available_and_price_below"),
            default="available_and_price_below",
            help="price_below ignoruje dostępność; domyślny typ wymaga dostępności",
        )
        cmd.add_argument("--drop", type=money)
        cmd.add_argument("--percent", type=int)
        cmd.add_argument("--restock", action="store_true")
        cmd.add_argument("--cooldown", type=int, default=21600)
    cmd = sub.add_parser("check")
    cmd.add_argument("id", type=int, nargs="?")
    cmd.add_argument(
        "--url",
        type=product_url_argument,
        help="Dodaj link, jeśli go nie ma, i sprawdź bez Discorda",
    )
    cmd.add_argument("--notify", action="store_true")
    cmd = sub.add_parser("verify-store", help="Jednorazowa diagnoza bez historii cen")
    cmd.add_argument("url", type=product_url_argument)
    cmd.add_argument("--output", type=Path)
    for name in ("pause", "resume", "remove", "history", "chart", "retry-alerts"):
        cmd = sub.add_parser(name)
        cmd.add_argument("id", type=int)
        if name == "chart":
            cmd.add_argument("output", type=Path)
        if name in ("chart", "history"):
            cmd.add_argument("--gap-hours", type=float, default=36)
    cmd = sub.add_parser("link")
    cmd.add_argument("id", type=int)
    cmd.add_argument("other", type=int)
    cmd.add_argument("--confirm-identical", action="store_true", required=True)
    cmd = sub.add_parser("compare")
    cmd.add_argument("product_id", type=int)
    for name in ("list", "status", "deliver", "bot", "test-webhook", "daily", "watchlist"):
        sub.add_parser(name)
    cmd = sub.add_parser("report")
    cmd.add_argument("period", choices=("daily", "weekly"), nargs="?")
    cmd.add_argument("--notify", action="store_true")
    cmd = sub.add_parser("export")
    cmd.add_argument("output", type=Path)
    cmd.add_argument("--format", choices=("csv", "json"), default="json")
    for name in ("snapshot", "restore"):
        cmd = sub.add_parser(name)
        cmd.add_argument("path", type=Path)
        if name == "snapshot":
            cmd.add_argument("--public", action="store_true")
            cmd.add_argument("--ack-public-data", action="store_true")
    return p


def execute(args, db, settings):
    if args.command == "test-webhook":
        return test_webhook(settings.webhook)
    if args.command == "verify-store":
        return StoreVerifier(db, settings).verify(args.url, args.output)
    service = Monitor(db, settings)
    command = args.command
    if command == "daily":
        return daily(service, settings.webhook)
    if command == "watchlist":
        return {"waluta": "PLN", "strefa_czasowa": "Europe/Warsaw", "oferty": watchlist(db)}
    if command in ("add", "edit"):
        rule = Subscription(
            rule_type=args.rule_type,
            target=args.target,
            drop_amount=args.drop,
            drop_percent=args.percent,
            restock=args.restock,
            cooldown=args.cooldown,
        )
        if command == "add":
            return {"id": service.add(args.url, rule)}
        service.edit(args.id, rule)
        return {"status": "reguły zastąpione"}
    if command == "check":
        if args.url and args.id:
            raise ValueError("Podaj id albo --url")
        if args.url:
            rows = db.rows("SELECT id FROM offers WHERE url=?", (args.url,))
            oid = rows[0]["id"] if rows else service.add(args.url, Subscription())
            result = [service.check(oid)]
        else:
            result = [service.check(args.id)] if args.id else service.check_all()
        output = {"kontrole": result}
        if args.notify:
            if not settings.webhook:
                raise ValueError("--notify wymaga DISCORD_WEBHOOK_URL")
            output["alerty"] = deliver(db, settings.webhook)
        return output
    if command in ("list", "status"):
        return service.status()
    if command in ("pause", "resume"):
        service.pause(args.id, command == "pause")
    elif command == "remove":
        service.remove(args.id)
    elif command == "link":
        service.link(args.id, args.other)
    elif command == "compare":
        return compare(db, args.product_id)
    elif command == "history":
        return history(db, args.id, gap_hours=args.gap_hours)
    elif command == "chart":
        chart(db, args.id, args.output, gap_hours=args.gap_hours)
    elif command == "export":
        export_data(db, args.output, args.format)
    elif command == "report":
        if args.period is None:
            if args.notify:
                raise ValueError("report --notify wymaga okresu daily albo weekly")
            return brief_report(service)
        if args.notify and not settings.webhook:
            raise ValueError("--notify wymaga DISCORD_WEBHOOK_URL")
        return report(db, args.period, webhook=settings.webhook if args.notify else None)
    elif command == "deliver":
        if not settings.webhook:
            raise ValueError("Ustaw DISCORD_WEBHOOK_URL")
        return deliver(db, settings.webhook)
    elif command == "retry-alerts":
        with db.conn:
            cursor = db.conn.execute(
                "UPDATE alerts SET state='pending',attempts=0,next_attempt="
                "datetime('now') WHERE id=? AND state='failed'",
                (args.id,),
            )
            if not cursor.rowcount:
                raise ValueError("Nie ma nieudanego alertu o tym id")
    elif command == "snapshot":
        if args.public and not args.ack_public_data:
            raise ValueError("Publiczny snapshot wymaga --ack-public-data")
        if args.public:
            # Jedyny obsługiwany cel to nazwa konfiguracji env, nigdy ID ani sekret.
            for row in db.rows("SELECT body FROM subscriptions"):
                if Subscription.model_validate_json(row["body"]).destination != "default":
                    raise ValueError("Publiczny snapshot nie może zawierać identyfikatorów Discord")
        save_snapshot(db, args.path)
    elif command == "restore":
        db.restore(json.loads(args.path.read_text(encoding="utf-8")), source=args.path)
    return {"status": "ok"}


def main():
    args = parser().parse_args()
    settings = Settings()
    path = args.db or settings.db
    try:
        if args.command == "test-webhook":
            print(json.dumps(execute(args, None, settings), ensure_ascii=False, indent=2))
            return 0
        with process_lock(path.with_suffix(".lock")):
            db = Database(path)
            try:
                if args.command == "bot":
                    from .discord_bot import run

                    run(db, settings)
                    return 0
                result = execute(args, db, settings)
                if isinstance(result, str):
                    print(result)
                else:
                    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
                if isinstance(result, dict) and "kontrole" in result:
                    return int(
                        any(r["status"] not in ("ok", "wstrzymana") for r in result["kontrole"])
                        or result.get("alerty", {}).get("błędy", 0) > 0
                    )
                if args.command == "deliver":
                    return int(result["błędy"] > 0)
                if args.command == "verify-store":
                    return 2 if result["status"] == "rejected" else int(result["status"] != "ok")
                return 0
            finally:
                db.close()
    except (ValueError, ReadError, OSError, sqlite3.Error) as exc:
        # Wyjątki transportu mają tylko bezpieczny kod, bez URL-i sekretów.
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
