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
# BOT (SLASH ONLY · SIN PRIVILEGIADOS)
# =========================
intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix=None,
    intents=intents
)

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
# PRECIOS BASE (USD)
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
# EMBED BUILDER
# =========================
def build_price_embed(moneda: str, rate: float):

    embed = discord.Embed(
        title="🛒 TIENDA MESSI",
        description="Elegí tu pack y hablá con el staff\n",
        color=BRAND_COLOR
    )

    pavos_text = ""
    for name, usd in PAVOS.items():
        price = usd if moneda == "USD" else smart_round(usd * rate)

        label = name
        if "5.000" in name:
            label += " ⭐ Mejor Oferta"
        if "13.500" in name:
            label += " 🔥 Más Vendida"

        pavos_text += f"{label}\n{price} {moneda}\n\n"

    embed.add_field(
        name="🪙 PAVOS",
        value=pavos_text,
        inline=False
    )

    club_text = ""
    for name, usd in CLUB.items():
        price = usd if moneda == "USD" else smart_round(usd * rate)
        club_text += f"{name}\n{price} {moneda}\n\n"

    embed.add_field(
        name="🎟️ CLUB FORTNITE",
        value=club_text,
        inline=False
    )

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
            placeholder="Seleccioná tu moneda",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        moneda = self.values[0]

        rate = 1
        if moneda != "USD":
            rate = await get_rate(moneda)

        embed = build_price_embed(moneda, rate)
        await interaction.response.edit_message(embed=embed, view=self.view)

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
@bot.tree.command(name="setup", description="Publicar panel de precios")
async def setup(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    embed = build_price_embed("USD", 1)
    view = CurrencyView()

    await interaction.response.send_message(embed=embed, view=view)

# =========================
# BALANCE
# =========================
@bot.tree.command(name="balance", description="Ver tu balance")
async def balance(interaction: discord.Interaction):

    data = load_json(BALANCE_FILE)
    amount = data.get(str(interaction.user.id), 0)

    embed = discord.Embed(
        title="💎 BALANCE DISPONIBLE",
        color=BRAND_COLOR
    )

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

    medals=["🥇","🥈","🥉"]
    text=""

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
