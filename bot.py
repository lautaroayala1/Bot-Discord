import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import time
import math
import os
from pathlib import Path

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")
BRAND_COLOR = discord.Color.from_str("#2B0A4D")

BALANCE_FILE = Path("balances.json")
POINTS_FILE = Path("points.json")

# =========================
# BOT (SLASH ONLY · SIN INTENTS PRIVILEGIADOS)
# =========================
INTENTS = discord.Intents.default()

bot = commands.Bot(
    command_prefix=None,
    intents=INTENTS
)

# =========================
# CACHE (1 MIN)
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
# REDONDEO INTELIGENTE
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
# PRECIOS BASE USD
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

MONEDAS = ["USD","EUR","ARS","CLP","PEN","COP","BRL","MXN"]

# =========================
# JSON HELPERS
# =========================
def load_json(file):
    if not file.exists():
        file.write_text("{}")
    return json.loads(file.read_text())

def save_json(file, data):
    file.write_text(json.dumps(data, indent=2))

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot listo como {bot.user}")

# =========================
# /setup (CONVERSION AUTOMATICA)
# =========================
@bot.tree.command(name="setup", description="Publicar panel de precios")
@app_commands.describe(moneda="Elegí la moneda")
async def setup(interaction: discord.Interaction, moneda: str):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    moneda = moneda.upper()

    if moneda not in MONEDAS:
        return await interaction.response.send_message("❌ Moneda no válida.", ephemeral=True)

    rate = 1
    if moneda != "USD":
        rate = await get_rate(moneda)

    embed = discord.Embed(
        title="🛒 TIENDA MESSI",
        description="Seleccioná tu pack y contactá al staff",
        color=BRAND_COLOR
    )

    text_pavos = ""
    for nombre, usd in PAVOS.items():
        precio = usd if moneda == "USD" else smart_round(usd * rate)

        if "5.000" in nombre:
            nombre += " ⭐ Mejor Oferta"
        if "13.500" in nombre:
            nombre += " 🔥 Más Vendida"

        text_pavos += f"{nombre} — {precio} {moneda}\n\n"

    embed.add_field(name="🪙 PAVOS", value=text_pavos, inline=False)

    text_club = ""
    for nombre, usd in CLUB.items():
        precio = usd if moneda == "USD" else smart_round(usd * rate)
        text_club += f"{nombre} — {precio} {moneda}\n\n"

    embed.add_field(name="🎟️ CLUB FORTNITE", value=text_club, inline=False)

    embed.set_footer(text="Messi Store • Sistema automático")

    await interaction.response.send_message(embed=embed)

# =========================
# /balance
# =========================
@bot.tree.command(name="balance", description="Ver tu balance")
async def balance(interaction: discord.Interaction):

    data = load_json(BALANCE_FILE)
    amount = data.get(str(interaction.user.id), 0)

    embed = discord.Embed(title="💎 BALANCE DISPONIBLE", color=BRAND_COLOR)
    embed.add_field(name="👤 Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="🪙 V-Bucks", value=f"**{amount:,}**", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# /addbalance
# =========================
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
# PUNTOS
# =========================
def add_points(uid, pts):
    data = load_json(POINTS_FILE)
    uid = str(uid)

    if uid not in data:
        data[uid] = {"total":0,"history":[]}

    data[uid]["total"] += pts
    data[uid]["history"].append({"points":pts,"timestamp":time.time()})
    save_json(POINTS_FILE,data)

def get_points(uid):
    data = load_json(POINTS_FILE)
    return data.get(str(uid),{}).get("total",0)

@bot.tree.command(name="points", description="Ver tus puntos")
async def points(interaction: discord.Interaction):

    total = get_points(interaction.user.id)

    embed = discord.Embed(title="🪙 MESSI REWARDS", color=BRAND_COLOR)
    embed.add_field(name="Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="Puntos activos", value=f"**{total:,} pts**", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addpoints", description="Agregar puntos")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, puntos: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    add_points(usuario.id,puntos)
    total = get_points(usuario.id)

    embed = discord.Embed(title="✨ Puntos acreditados", color=BRAND_COLOR)
    embed.add_field(name="Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="Total actual", value=f"**{total:,} pts**", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ranks", description="Ranking mensual")
async def ranks(interaction: discord.Interaction):

    data = load_json(POINTS_FILE)
    now = time.time()
    ranking=[]

    for uid,info in data.items():
        monthly=sum(
            h["points"]
            for h in info.get("history",[])
            if now-h["timestamp"]<=30*86400
        )
        if monthly>0:
            ranking.append((int(uid),monthly))

    ranking.sort(key=lambda x:x[1],reverse=True)

    embed=discord.Embed(title="🏆 RANKING MENSUAL",color=BRAND_COLOR)

    text=""
    medals=["🥇","🥈","🥉"]

    for i,(uid,pts) in enumerate(ranking[:10]):
        medal=medals[i] if i<3 else "🔹"
        text+=f"{medal} <@{uid}> — **{pts:,} pts**\n\n"

    if not text:
        text="Todavía no hay puntos registrados."

    embed.add_field(name="Top Clientes",value=text,inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# START
# =========================
bot.run(TOKEN)
