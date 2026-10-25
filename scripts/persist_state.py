"""Commit i push wyłącznie danych; bez shell=True, force i ukrywania błędów."""

import argparse
import subprocess
from pathlib import Path


def persist(path: Path):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
        )

    git("config", "user.name", "price-sentinel[bot]")
    git("config", "user.email", "price-sentinel@users.noreply.github.com")
    git("add", "--", "snapshot.json")
    if git("status", "--porcelain", "--", "snapshot.json").stdout.strip():
        git("commit", "-m", "Update public monitoring snapshot", "--", "snapshot.json")
        # Odrzucenie push oznacza błąd całego workflow; nie nadpisujemy cudzych zmian.
        git("push", "origin", "HEAD:sentinel-data")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("checkout", type=Path)
    args = p.parse_args()
    try:
        persist(args.checkout)
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Zapis snapshotu nieudany. Zachowaj artefakt i rozwiąż konflikt ręcznie."
        ) from None
