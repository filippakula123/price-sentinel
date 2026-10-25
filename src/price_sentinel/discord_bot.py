"""Opcjonalny, stale działający proces. Nigdy nie uruchamiany w Actions."""

import asyncio
import json
import logging
import os

from .alerts import deliver
from .config import Settings
from .history import compare, history, report
from .models import Subscription, money
from .service import Monitor


def authorized(user_id: int, guild_id: int | None, owner: int, guild: int) -> bool:
    return user_id == owner and guild_id == guild


def run(db, settings: Settings):
    try:
        import discord
        from discord import app_commands
    except ImportError as exc:
        raise ValueError('Zainstaluj integrację: pip install -e ".[discord]"') from exc
    token = os.getenv("DISCORD_BOT_TOKEN")
    owner = int(os.getenv("DISCORD_OWNER_ID", "0"))
    guild_id = int(os.getenv("DISCORD_GUILD_ID", "0"))
    if not token or not owner or not guild_id:
        raise ValueError("Ustaw DISCORD_BOT_TOKEN, DISCORD_OWNER_ID i DISCORD_GUILD_ID")
    guild = discord.Object(id=guild_id)
    service = Monitor(db, settings)
    operation_lock = asyncio.Lock()

    class Client(discord.Client):
        async def setup_hook(self):
            self.tree = app_commands.CommandTree(self)

            async def guard(interaction):
                if not authorized(interaction.user.id, interaction.guild_id, owner, guild_id):
                    await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
                    return False
                return True

            async def respond(interaction, action):
                if not await guard(interaction):
                    return
                await interaction.response.defer(ephemeral=True)
                try:
                    async with operation_lock:
                        value = await asyncio.to_thread(action)
                    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
                    if len(text) > 1800:
                        import io

                        await interaction.followup.send(
                            file=discord.File(io.BytesIO(text.encode()), filename="wynik.json"),
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(
                            text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
                        )
                except (ValueError, OSError):
                    await interaction.followup.send(
                        "Niepoprawne dane lub błąd operacji.", ephemeral=True
                    )

            @self.tree.command(name="lista", description="Oferty i ostatnie poprawne odczyty")
            async def lista(interaction: discord.Interaction):
                await respond(interaction, service.status)

            @self.tree.command(
                name="sprawdz", description="Sprawdź ofertę i obsłuż kolejkę alertów"
            )
            async def sprawdz(interaction: discord.Interaction, oferta: int):
                def action():
                    result = service.check(oferta)
                    return {"kontrola": result, "alerty": deliver(db, settings.webhook)}

                await respond(interaction, action)

            @self.tree.command(name="dodaj", description="Dodaj konkretny link HTTPS")
            async def dodaj(interaction: discord.Interaction, url: str, cel: str | None = None):
                await respond(
                    interaction,
                    lambda: {
                        "id": service.add(url, Subscription(target=money(cel) if cel else None))
                    },
                )

            @self.tree.command(name="edytuj", description="Zastąp reguły alertów oferty")
            async def edytuj(
                interaction: discord.Interaction,
                oferta: int,
                cel: str | None = None,
                spadek: str | None = None,
                procent: int | None = None,
                powrot: bool = False,
            ):
                await respond(
                    interaction,
                    lambda: service.edit(
                        oferta,
                        Subscription(
                            target=money(cel) if cel else None,
                            drop_amount=money(spadek) if spadek else None,
                            drop_percent=procent,
                            restock=powrot,
                        ),
                    ),
                )

            @self.tree.command(name="wstrzymaj", description="Wstrzymaj lub wznów obserwowanie")
            async def wstrzymaj(interaction: discord.Interaction, oferta: int, pauza: bool = True):
                await respond(interaction, lambda: service.pause(oferta, pauza))

            @self.tree.command(name="usun", description="Usuń ofertę i jej historię")
            async def usun(interaction: discord.Interaction, oferta: int):
                await respond(interaction, lambda: service.remove(oferta))

            @self.tree.command(name="historia", description="Historia, minima i luki")
            async def historia(interaction: discord.Interaction, oferta: int):
                await respond(interaction, lambda: history(db, oferta))

            @self.tree.command(name="porownaj", description="Porównaj ręcznie powiązane oferty")
            async def porownaj(interaction: discord.Interaction, produkt: int):
                await respond(interaction, lambda: compare(db, produkt))

            @self.tree.command(name="powiaz", description="Potwierdź identyczność dwóch wariantów")
            async def powiaz(
                interaction: discord.Interaction, oferta: int, druga: int, identyczne: bool
            ):
                if not identyczne:
                    await respond(interaction, lambda: "Najpierw sprawdź wariant i zestaw.")
                else:
                    await respond(interaction, lambda: service.link(oferta, druga))

            @self.tree.command(name="raport", description="Raport dzienny lub tygodniowy")
            async def raport(interaction: discord.Interaction, tygodniowy: bool = False):
                await respond(interaction, lambda: report(db, "weekly" if tygodniowy else "daily"))

            # Komendy tylko w jednym serwerze; dodatkowo każda ma guard właściciela.
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    # Kontrole na żądanie działają w workerze; wszystkie operacje bazy są serializowane.
    client = Client(intents=discord.Intents.none())
    logging.getLogger("discord").setLevel(logging.CRITICAL)
    try:
        client.run(token, log_handler=None)
    except discord.LoginFailure as exc:
        raise ValueError("Niepoprawny token Discord (ukryty)") from exc
