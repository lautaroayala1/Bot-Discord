import os
import discord
from discord.ext import commands
import aiohttp
import time
import math
import json
from pathlib import Path

# =========================
# TOKEN
# =========================
TOKEN = os.getenv("TOKEN")

# =========================
# MARCA
# =========================
PAVOS_EMOJI = "<:Pavos:1440841778373722213>"
BRAND_COLOR = discord.Color.from_str("#2B0A4D")

# =========================
# BOT
# =========================
intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix=None,
    intents=intents
)

# =========================
# SINCRONIZACIÓN AUTOMÁTICA
# =========================
@bot.event
async def on_ready():

    print(f"Conectado como {bot.user}")

    # Sync global
    await bot.tree.sync()

    # Sync por servidor (actualiza instantáneo)
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
        except:
            pass

    print("Comandos sincronizados.")


# =========================
# UTILIDADES
# =========================
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


# =========================
# PRECIOS
# =========================
PAVOS = {
    "1.000 Pavos": 6,
    "2.800 Pavos": 15,
    "5.000 Pavos": 28,
    "13.500 Pavos": 42,
}

CLUB = {
    "1 mes": 3,
    "3 meses": 9,
    "6 meses": 15,
}

MONEDAS = {
    "USD": "🇺🇸 USD",
    "EUR": "🇪🇺 EUR",
    "ARS": "🇦🇷 ARS",
    "CLP": "🇨🇱 CLP",
    "PEN": "🇵🇪 PEN",
    "COP": "🇨🇴 COP",
    "BRL": "🇧🇷 BRL",
    "MXN": "🇲🇽 MXN",
}

EMOJIS = {k: v.split()[0] for k, v in MONEDAS.items()}

# =========================
# CONVERSIÓN
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


# =========================
# BALANCE REGALOS
# =========================
BALANCE_FILE = Path("balances.json")
if not BALANCE_FILE.exists():
    BALANCE_FILE.write_text("{}")

def load_balances():
    return json.loads(BALANCE_FILE.read_text())

def save_balances(data):
    BALANCE_FILE.write_text(json.dumps(data, indent=2))

def get_balance(user_id):
    return load_balances().get(str(user_id), 0)

def set_balance(user_id, amount):
    data = load_balances()
    data[str(user_id)] = max(int(amount), 0)
    save_balances(data)


# =========================
# SISTEMA PUNTOS
# =========================
POINTS_FILE = Path("points.json")
if not POINTS_FILE.exists():
    POINTS_FILE.write_text("{}")

def load_points():
    return json.loads(POINTS_FILE.read_text())

def save_points(data):
    POINTS_FILE.write_text(json.dumps(data, indent=2))

def get_points_data(user_id):
    return load_points().get(str(user_id), {
        "points": 0,
        "history": [],
        "last_purchase": 0
    })

def save_user_points(user_id, user_data):
    data = load_points()
    data[str(user_id)] = user_data
    save_points(data)

def get_level(points):
    if points >= 300:
        return "🥇 Oro"
    elif points >= 100:
        return "🥈 Plata"
    return "🥉 Bronce"

def add_points(user_id, base_points, product_name=""):
    user = get_points_data(user_id)
    now = time.time()

    multiplier = 1
    if "5.000" in product_name:
        multiplier = 2
    elif "13.500" in product_name:
        multiplier = 1.5

    earned = int(base_points * multiplier)

    if now - user["last_purchase"] <= 14 * 86400:
        earned += 10

    user["history"].append({
        "points": earned,
        "timestamp": now
    })

    user["last_purchase"] = now

    valid = []
    total = 0

    for entry in user["history"]:
        if now - entry["timestamp"] <= 30 * 86400:
            valid.append(entry)
            total += entry["points"]

    user["history"] = valid
    user["points"] = total

    save_user_points(user_id, user)
    return earned, total


# =========================
# SELECTOR MONEDA
# =========================
class CurrencySelect(discord.ui.Select):
    def __init__(self, precios, titulo):
        self.precios = precios
        self.titulo = titulo

        options = [
            discord.SelectOption(label=MONEDAS[c], value=c, emoji=EMOJIS[c])
            for c in MONEDAS
        ]

        super().__init__(placeholder="Elegí tu moneda", options=options)

    async def callback(self, interaction: discord.Interaction):
        moneda = self.values[0]
        rate = 1 if moneda == "USD" else await get_rate(moneda)

        embed = discord.Embed(color=BRAND_COLOR)
        embed.title = self.titulo

        description = ""

        for nombre, usd in self.precios.items():
            valor = usd * rate
            if moneda not in ("USD", "EUR"):
                valor = smart_round(valor)

            formatted = f"{valor:,.2f}" if moneda == "EUR" else f"{valor:,.0f}"
            description += f"**{nombre}**\n{EMOJIS[moneda]} {formatted} {moneda}\n\n"

        embed.description = description.strip()
        embed.set_footer(text="Base USD · Conversión automática")

        await interaction.response.send_message(embed=embed, ephemeral=True)

class CurrencyView(discord.ui.View):
    def __init__(self, precios, titulo):
        super().__init__(timeout=None)
        self.add_item(CurrencySelect(precios, titulo))


# =========================
# /setup
# =========================
@bot.tree.command(name="setup", description="Configura el canal de precios")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):

    guild = interaction.guild
    canal = discord.utils.get(guild.text_channels, name="precios")

    if not canal:
        canal = await guild.create_text_channel("precios")

    embed_pavos = discord.Embed(
        title="🪙 Pavos Fortnite",
        description="Seleccioná tu moneda debajo",
        color=BRAND_COLOR
    )

    await canal.send(embed=embed_pavos, view=CurrencyView(PAVOS, "🪙 Pavos Fortnite"))
    await canal.send("\u200b")

    embed_club = discord.Embed(
        title="🎟️ Club Fortnite",
        description="Seleccioná tu moneda debajo",
        color=BRAND_COLOR
    )

    await canal.send(embed=embed_club, view=CurrencyView(CLUB, "🎟️ Club Fortnite"))

    await interaction.response.send_message("Canal configurado.", ephemeral=True)


# =========================
# /balance
# =========================
@bot.tree.command(name="balance", description="Tu balance")
async def balance(interaction: discord.Interaction, usuario: discord.Member | None = None):

    target = usuario or interaction.user
    saldo = get_balance(target.id)

    embed = discord.Embed(color=BRAND_COLOR)
    embed.title = "Balance"

    embed.description = (
        f"{target.mention}\n\n"
        f"Disponible\n"
        f"**{saldo:,} V-Bucks**"
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /points
# =========================
@bot.tree.command(name="points", description="Tus puntos")
async def points(interaction: discord.Interaction, usuario: discord.Member | None = None):

    target = usuario or interaction.user
    add_points(target.id, 0)

    data = get_points_data(target.id)
    total = data["points"]

    embed = discord.Embed(color=BRAND_COLOR)
    embed.title = "Messi Rewards"

    embed.description = (
        f"{target.mention}\n\n"
        f"Puntos activos\n"
        f"**{total}**\n\n"
        f"Nivel\n"
        f"{get_level(total)}"
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /addpoints
# =========================
@bot.tree.command(name="addpoints", description="Acredita puntos")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, producto: str, puntos_base: int):

    earned, total = add_points(usuario.id, puntos_base, producto)

    embed = discord.Embed(color=BRAND_COLOR)
    embed.title = "Puntos acreditados"

    embed.description = (
        f"{usuario.mention}\n\n"
        f"+{earned} puntos\n\n"
        f"Total\n"
        f"{total}"
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /ranks
# =========================
@bot.tree.command(name="ranks", description="Ranking mensual")
async def ranks(interaction: discord.Interaction):

    data = load_points()
    now = time.time()
    ranking = []

    for user_id, info in data.items():
        monthly = sum(
            entry["points"]
            for entry in info.get("history", [])
            if now - entry["timestamp"] <= 30 * 86400
        )
        if monthly > 0:
            ranking.append((int(user_id), monthly))

    ranking.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(color=BRAND_COLOR)
    embed.title = "Ranking mensual"

    if not ranking:
        embed.description = "Sin puntos este mes."
        return await interaction.response.send_message(embed=embed)

    description = ""

    for i, (uid, pts) in enumerate(ranking[:10], 1):
        member = interaction.guild.get_member(uid)
        name = member.display_name if member else str(uid)
        description += f"{i}. **{name}** — {pts}\n"

    embed.description = description.strip()
    await interaction.response.send_message(embed=embed)


# =========================
# RUN
# =========================
bot.run(TOKEN)
