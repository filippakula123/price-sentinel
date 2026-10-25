import importlib.util
import subprocess
from pathlib import Path

import httpx
import pytest

from price_sentinel.alerts import send_webhook
from price_sentinel.config import Settings
from price_sentinel.discord_bot import run
from price_sentinel.transport import ReadError

WEBHOOK = "https://discord.com/api/webhooks/123/synthetic_not_a_secret"


@pytest.mark.parametrize("status", [204, 302, 403, 429])
def test_webhook_payload_and_errors(status, monkeypatch):
    real_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status)

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle))
    )
    if status == 204:
        send_webhook(WEBHOOK, "Cena spadła @everyone")
    else:
        with pytest.raises(ReadError) as exc:
            send_webhook(WEBHOOK, "test")
        assert WEBHOOK not in str(exc.value)
        assert str(status) in str(exc.value)
    import json

    assert json.loads(requests[0].content)["allowed_mentions"] == {"parse": []}
    assert len(requests) == 1  # Żadnego podążania za redirectem webhooka.


def test_discord_commands_register_offline(db, monkeypatch):
    discord = pytest.importorskip("discord")
    from discord import app_commands

    names = []
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "synthetic")
    monkeypatch.setenv("DISCORD_OWNER_ID", "123")
    monkeypatch.setenv("DISCORD_GUILD_ID", "456")

    async def sync(tree, *, guild):
        names.extend(c.name for c in tree.get_commands(guild=guild))
        return []

    monkeypatch.setattr(app_commands.CommandTree, "sync", sync)

    def offline(client, token, **kwargs):
        assert token == "synthetic"
        # Jedyny await (sync) kończy się od razu. Event loop na Windows używa
        # lokalnych socketów TCP, których testy celowo nie dopuszczają.
        coroutine = client.setup_hook()
        try:
            with pytest.raises(StopIteration):
                coroutine.send(None)
        finally:
            coroutine.close()

    monkeypatch.setattr(discord.Client, "run", offline)
    run(db, Settings())
    assert set(names) == {
        "lista",
        "dodaj",
        "edytuj",
        "wstrzymaj",
        "usun",
        "sprawdz",
        "historia",
        "porownaj",
        "powiaz",
        "raport",
    }


def test_local_git_snapshot_persistence_and_conflict(tmp_path):
    """Prawdziwy lokalny git, bez GitHuba/sieci; konflikt nie może zniknąć."""
    spec = importlib.util.spec_from_file_location("persist_state", Path("scripts/persist_state.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def git(*args, cwd=None):
        return subprocess.run(
            ["git", *map(str, args)], cwd=cwd, check=True, capture_output=True, text=True
        )

    remote, first, second = [tmp_path / name for name in ("remote.git", "first", "second")]
    git("init", "--bare", remote)
    git("clone", remote, first)
    git("switch", "-c", "sentinel-data", cwd=first)
    (first / "snapshot.json").write_text('{"version":1}', encoding="utf-8")
    module.persist(first)
    git("clone", "--branch", "sentinel-data", remote, second)
    (first / "snapshot.json").write_text('{"version":2}', encoding="utf-8")
    module.persist(first)
    assert '"version":2' in git("show", "sentinel-data:snapshot.json", cwd=remote).stdout
    (second / "snapshot.json").write_text('{"version":3}', encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        module.persist(second)
    assert '"version":2' in git("show", "sentinel-data:snapshot.json", cwd=remote).stdout
