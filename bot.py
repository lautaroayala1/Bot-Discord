import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import time
import math
import os
from pathlib import Path

TOKEN = os.getenv("TOKEN")
BRAND_COLOR = discord.Color.from_str("#2B0A4D")

BALANCE_FILE = Path("balances.json")
POINTS_FILE = Path("points.json")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

# =========================
# CACHE CAMBIO
# =========================
RATE_CACHE = {}
CACHE_TTL = 60

async def get_rate(to_currency: str):
    now = time.time()

    if to_currency in RATE_CACHE:
        rate, ts = RATE_CACHE[to_currency]
        if now - ts < CACHE_TTL:
            return rate

    async with aiohttp.ClientSession() as session:
        async with session.get("https://open.er-api.com/v6/latest/USD") as resp:
            data = await resp.json()
            rate = data["rates"][to_currency]
            RATE_CACHE[to_currency] = (rate, now)
            return rate

def smart_round(value: float) -> int:
    if value < 1_000:
        step = 10
    elif value < 10_000:
        step = 100
    elif value < 100_000:
        step = 1_000
    else:
        step = 10_000
    return int(math.ceil(value / step) * step)

PAVOS = {
    "🪙 1.000 Pavos": 6,
    "🪙 2.800 Pavos": 15,
    "🪙 5.000 Pavos": 28,
    "🪙 13.500 Pavos": 42,
}

CLUB = {
    "🎟️ 1 mes": 3,
    "🎟️ 3 meses": 9,
    "🎟️ 6 meses": 15,
}

MONEDAS = ["USD","EUR","ARS","CLP","PEN","COP","BRL","MXN"]

# =========================
# JSON
# =========================
def load_json(file):
    if not file.exists():
        file.write_text("{}")
    return json.loads(file.read_text())

def save_json(file, data):
    file.write_text(json.dumps(data, indent=2))

# =========================
# EMBEDS
# =========================
def build_pavos_embed(moneda, rate):

    embed = discord.Embed(
        title="🪙 PAVOS DISPONIBLES",
        color=BRAND_COLOR
    )

    text = ""

    for name, usd in PAVOS.items():
        price = usd if moneda == "USD" else smart_round(usd * rate)

        label = name
        if "5.000" in name:
            label += " ⭐ Mejor Oferta"
        if "13.500" in name:
            label += " 🔥 Más Vendida"

        text += f"{label}\n{price} {moneda}\n\n"

    embed.description = text
    embed.set_footer(text="Messi Store • Sistema automático")

    return embed


def build_club_embed(moneda, rate):

    embed = discord.Embed(
        title="🎟️ CLUB FORTNITE",
        color=BRAND_COLOR
    )

    text = ""

    for name, usd in CLUB.items():
        price = usd if moneda == "USD" else smart_round(usd * rate)
        text += f"{name}\n{price} {moneda}\n\n"

    embed.description = text
    embed.set_footer(text="Messi Store • Sistema automático")

    return embed

# =========================
# SELECTOR MONEDA
# =========================
class CurrencySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=m, emoji="💱")
            for m in MONEDAS
        ]

        super().__init__(
            placeholder="Ver precios en tu moneda",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        moneda = self.values[0]

        rate = 1
        if moneda != "USD":
            rate = await get_rate(moneda)

        pavos_embed = build_pavos_embed(moneda, rate)
        club_embed = build_club_embed(moneda, rate)

        await interaction.response.send_message(embed=pavos_embed)
        await interaction.followup.send(embed=club_embed)

class CurrencyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CurrencySelect())

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot listo como {bot.user}")

# =========================
# /setup
# =========================
@bot.tree.command(name="setup", description="Crear o usar canal precios y publicar panel")
async def setup(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    guild = interaction.guild
    channel = discord.utils.get(guild.text_channels, name="precios")

    if not channel:
        channel = await guild.create_text_channel("precios")

    base_embed = discord.Embed(
        title="🛒 TIENDA MESSI",
        description="Seleccioná tu moneda abajo para ver precios actualizados.",
        color=BRAND_COLOR
    )

    view = CurrencyView()

    await channel.send(embed=base_embed, view=view)

    await interaction.response.send_message(
        f"✅ Panel publicado en {channel.mention}",
        ephemeral=True
    )

# =========================
# BALANCE
# =========================
@bot.tree.command(name="balance", description="Ver tu balance")
async def balance(interaction: discord.Interaction):

    data = load_json(BALANCE_FILE)
    amount = data.get(str(interaction.user.id), 0)

    embed = discord.Embed(title="💎 BALANCE", color=BRAND_COLOR)
    embed.add_field(name="Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="V-Bucks", value=f"**{amount:,}**", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addbalance", description="Agregar balance")
async def addbalance(interaction: discord.Interaction, usuario: discord.Member, cantidad: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    data = load_json(BALANCE_FILE)
    uid = str(usuario.id)
    data[uid] = data.get(uid, 0) + cantidad
    save_json(BALANCE_FILE, data)

    embed = discord.Embed(title="✨ Balance actualizado", color=BRAND_COLOR)
    embed.add_field(name="Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="Nuevo total", value=f"**{data[uid]:,} V-Bucks**", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# START
# =========================
bot.run(TOKEN)
