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
INTENTS = discord.Intents.default()

bot = commands.Bot(
    command_prefix=None,
    intents=INTENTS
)

# =========================
# CACHE CONVERSION
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

# =========================
# PRECIOS BASE
# =========================
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

def get_balance(user_id: int):
    return load_balances().get(str(user_id), 0)

def set_balance(user_id: int, amount: int):
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

def get_points_data(user_id: int):
    return load_points().get(str(user_id), {
        "points": 0,
        "history": [],
        "last_purchase": 0
    })

def save_user_points(user_id: int, user_data):
    data = load_points()
    data[str(user_id)] = user_data
    save_points(data)

def get_user_level(points: int):
    if points >= 300:
        return "🥇 Oro"
    elif points >= 100:
        return "🥈 Plata"
    return "🥉 Bronce"

def add_points(user_id: int, base_points: int, product_name=""):
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

    valid_history = []
    total = 0

    for entry in user["history"]:
        if now - entry["timestamp"] <= 30 * 86400:
            valid_history.append(entry)
            total += entry["points"]

    user["history"] = valid_history
    user["points"] = total

    save_user_points(user_id, user)
    return earned, total

# =========================
# PERMISOS
# =========================
def is_staff_or_owner(interaction):
    allowed = {"staff", "owner"}
    roles = {r.name.lower() for r in interaction.user.roles}
    return not allowed.isdisjoint(roles)

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Conectado como {bot.user}")

# =========================
# /balance
# =========================
@bot.tree.command(name="balance", description="Muestra tu balance")
async def balance(interaction: discord.Interaction, usuario: discord.Member | None = None):

    target = usuario or interaction.user
    saldo = get_balance(target.id)

    embed = discord.Embed(
        title=f"{PAVOS_EMOJI} V-BUCKS BALANCE",
        description=(
            f"👤 Usuario:\n"
            f"{target.mention}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"{PAVOS_EMOJI} Balance disponible:\n\n"
            f"✨ {saldo:,} V-Bucks\n\n"
            f"━━━━━━━━━━━━━━━━━━"
        ),
        color=BRAND_COLOR
    )

    embed.set_footer(text="Sistema interno de regalos")
    await interaction.response.send_message(embed=embed)

# =========================
# /points
# =========================
@bot.tree.command(name="points", description="Muestra tus puntos")
async def points(interaction: discord.Interaction, usuario: discord.Member | None = None):

    target = usuario or interaction.user

    # Limpia vencidos
    add_points(target.id, 0)

    data = get_points_data(target.id)
    total = data["points"]
    nivel = get_user_level(total)

    embed = discord.Embed(
        title="🏆 🪙 MESSI REWARDS",
        description=(
            f"👤 Cliente:\n"
            f"{target.mention}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🪙 Puntos disponibles:\n\n"
            f"✨ {total} puntos\n\n"
            f"🏅 Nivel actual:\n"
            f"{nivel}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"100 puntos = US$5 descuento\n"
            f"Vencen a los 30 días"
        ),
        color=BRAND_COLOR
    )

    embed.set_footer(text="Programa oficial de beneficios")
    await interaction.response.send_message(embed=embed)

# =========================
# /addpoints
# =========================
@bot.tree.command(name="addpoints", description="Acredita puntos")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, producto: str, puntos_base: int):

    if not is_staff_or_owner(interaction):
        return await interaction.response.send_message("Sin permisos.", ephemeral=True)

    ganados, total = add_points(usuario.id, puntos_base, producto)

    embed = discord.Embed(
        title="🏆 🪙 MESSI REWARDS",
        description=(
            f"👤 Cliente:\n{usuario.mention}\n\n"
            f"🛍️ Producto:\n{producto}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✨ +{ganados} puntos acreditados\n\n"
            f"🏅 Total actual:\n{total} puntos\n"
            f"{get_user_level(total)}"
        ),
        color=BRAND_COLOR
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

        monthly_points = 0

        for entry in info.get("history", []):
            if now - entry["timestamp"] <= 30 * 86400:
                monthly_points += entry["points"]

        if monthly_points > 0:
            ranking.append((int(user_id), monthly_points))

    ranking.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆 RANKING MENSUAL",
        description="Clientes con más puntos en los últimos 30 días",
        color=BRAND_COLOR
    )

    if not ranking:
        embed.add_field(
            name="Sin datos aún",
            value="Todavía no hay puntos registrados este mes.",
            inline=False
        )
        return await interaction.response.send_message(embed=embed)

    table = "```"
    table += "POS  |  CLIENTE                |  PUNTOS\n"
    table += "-------------------------------------------\n"

    for i, (user_id, points) in enumerate(ranking[:10], start=1):

        member = interaction.guild.get_member(user_id)
        name = member.display_name if member else f"ID {user_id}"
        name = name[:20].ljust(20)

        table += f"{str(i).ljust(4)} | {name} | {points}\n"

    table += "```"

    embed.add_field(
        name="Top 10",
        value=table,
        inline=False
    )

    embed.set_footer(text="Ranking basado en puntos activos (30 días)")
    await interaction.response.send_message(embed=embed)

# =========================
# RUN
# =========================
bot.run(TOKEN)
