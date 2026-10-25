import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .alerts import pln, send_webhook
from .models import Observation, now

WARSAW = ZoneInfo("Europe/Warsaw")


def history(db, oid: int, *, days: int = 90, gap_hours: float = 36) -> dict:
    db.offer(oid)
    start = datetime.now(UTC) - timedelta(days=days)
    rows = db.rows(
        "SELECT body FROM observations WHERE offer_id=? AND at>=? ORDER BY at,id",
        (oid, start.isoformat()),
    )
    points = [Observation.model_validate_json(r["body"]) for r in rows]
    gaps = []
    checks = db.rows(
        "SELECT at,status FROM checks WHERE offer_id=? AND at>=? ORDER BY at,id",
        (oid, start.isoformat()),
    )
    for check in checks:
        if check["status"] != "ok":
            gaps.append({"od": check["at"], "do": check["at"], "powód": check["status"]})
    for a, b in zip(points, points[1:], strict=False):
        if (datetime.fromisoformat(b.at) - datetime.fromisoformat(a.at)).total_seconds() > (
            gap_hours * 3600
        ):
            gaps.append({"od": a.at, "do": b.at, "powód": "przerwa_w_monitorowaniu"})
    if points and (datetime.now(UTC) - datetime.fromisoformat(points[-1].at)).total_seconds() > (
        gap_hours * 3600
    ):
        gaps.append({"od": points[-1].at, "do": now(), "powód": "brak_świeżego_odczytu"})
    minima = {}
    for window in (7, 30, 90):
        cutoff = datetime.now(UTC) - timedelta(days=window)
        prices = [p.price for p in points if datetime.fromisoformat(p.at) >= cutoff]
        minima[str(window)] = min(prices) if len(prices) >= 2 else None
    return {
        "status": "ok" if len(points) >= 2 else "za mało danych",
        "od": points[0].at if points else None,
        "do": points[-1].at if points else None,
        "liczba_obserwacji": len(points),
        "minima_grosze": minima,
        "luki": gaps,
        "obserwacje": [p.model_dump() for p in points],
    }


def compare(db, product_id: int) -> list[dict]:
    result = []
    for offer in db.rows("SELECT * FROM offers WHERE product_id=? ORDER BY id", (product_id,)):
        rows = db.rows(
            "SELECT body FROM observations WHERE offer_id=? ORDER BY id DESC LIMIT 1",
            (offer["id"],),
        )
        current = Observation.model_validate_json(rows[0]["body"]) if rows else None
        result.append(
            {
                "id": offer["id"],
                "url": offer["url"],
                "status": offer["status"],
                "ostatni_sukces": offer["last_success"],
                "ostatnia_obserwacja": current.model_dump() if current else None,
                "razem_grosze": current.price + current.shipping
                if current and current.shipping is not None
                else None,
            }
        )
    return result


def export_data(db, path: Path, fmt: str):
    rows = db.rows(
        "SELECT o.offer_id,f.url,o.at,o.body FROM observations o "
        "JOIN offers f ON f.id=o.offer_id ORDER BY o.at,o.id"
    )
    result = [{"offer_id": r["offer_id"], "url": r["url"], **json.loads(r["body"])} for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        buffer = io.StringIO(newline="")
        fields = ["offer_id", "url", *Observation.model_fields]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in result:
            # Bezpieczny eksport do arkuszy: ochrona przed formułami CSV.
            writer.writerow(
                {
                    k: "'" + v
                    if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                    for k, v in row.items()
                }
            )
        path.write_text(buffer.getvalue(), encoding="utf-8-sig")


def chart(db, oid: int, path: Path, *, gap_hours: float = 36):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    data = history(db, oid, gap_hours=gap_hours)
    points = [Observation.model_validate(p) for p in data["obserwacje"]]
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    xs, ys = [], []
    previous = None
    for point in points:
        dt = datetime.fromisoformat(point.at)
        if previous:
            # Przerywamy linię także przy zarejestrowanym nieudanym odczycie.
            failed = any(previous.isoformat() <= g["od"] <= point.at for g in data["luki"])
            if failed or (dt - previous).total_seconds() > gap_hours * 3600:
                xs.append(dt)
                ys.append(float("nan"))
        xs.append(dt)
        ys.append(point.price / 100)
        previous = dt
    ax.plot(xs, ys, marker="o", label="Własne obserwacje")
    if points:
        first = datetime.fromisoformat(points[0].at)
        last = datetime.fromisoformat(points[-1].at)
        padding = max(timedelta(minutes=30), (last - first) / 20)
        ax.set_xlim(first - padding, last + padding)
        locator = mdates.AutoDateLocator(minticks=3, maxticks=6, tz=UTC)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=UTC))
    for gap in data["luki"]:
        a, b = datetime.fromisoformat(gap["od"]), datetime.fromisoformat(gap["do"])
        if a == b:
            ax.axvline(a, color="orange", alpha=0.5)
        else:
            ax.axvspan(a, b, color="orange", alpha=0.2)
    ax.set_title(f"Oferta {oid}: {data['status']}\nPomarańczowy: luki lub błędy odczytu")
    ax.set_ylabel("Cena PLN (dostawa osobno)")
    ax.set_xlabel("Czas UTC; historia od rozpoczęcia monitorowania")
    ax.grid(alpha=0.2)
    fig.autofmt_xdate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def report(db, period: str, *, webhook: str | None = None) -> str:
    local = datetime.now(WARSAW)
    days = 1 if period == "daily" else 7
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    label = "dzienny" if period == "daily" else "tygodniowy"
    lines = [
        f"Price Sentinel — raport {label}, {local:%Y-%m-%d %H:%M %Z}",
        f"Ruchome ostatnie {days} dni; ceny bez dostawy.",
    ]
    for offer in db.rows("SELECT * FROM offers ORDER BY id"):
        rows = db.rows(
            "SELECT body FROM observations WHERE offer_id=? AND at>=? ORDER BY at",
            (offer["id"], cutoff),
        )
        points = [Observation.model_validate_json(r["body"]) for r in rows]
        price = pln(points[-1].price) if points else "brak odczytu w okresie"
        minimum = pln(min(p.price for p in points)) if len(points) >= 2 else "za mało danych"
        lines.append(
            f"#{offer['id']} {price}; minimum: {minimum}; "
            f"odczyty: {len(points)}; status: {offer['status']}; "
            f"ostatni sukces: {offer['last_success'] or 'brak'}\n{offer['url']}"
        )
    text = "\n".join(lines)
    if webhook:
        # Daty lokalne i tydzień ISO: poprawne klucze także przy zmianie czasu.
        key = (
            period
            + ":"
            + (local.strftime("%Y-%m-%d") if period == "daily" else local.strftime("%G-W%V"))
        )
        if not db.rows("SELECT key FROM report_runs WHERE key=?", (key,)):
            # Dzielenie po wierszach; bez obcinania długiej watchlisty.
            chunks, chunk = [], ""
            for line in lines:
                if len(chunk) + len(line) > 1800:
                    chunks.append(chunk)
                    chunk = ""
                chunk += line + "\n"
            if chunk:
                chunks.append(chunk)
            for part in chunks:
                send_webhook(webhook, part)
            with db.conn:
                db.conn.execute("INSERT INTO report_runs VALUES (?,?)", (key, now()))
    return text
