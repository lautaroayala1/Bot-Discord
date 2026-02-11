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
# EMBEDS
# =========================
def build_usd_pavos():
    embed = discord.Embed(title="🪙 PAVOS DISPONIBLES (USD)", color=BRAND_COLOR)
    text = ""
    for name, price in PAVOS.items():
        label = name
        if "5.000" in name:
            label += " ⭐ Mejor Oferta"
        if "13.500" in name:
            label += " 🔥 Más Vendida"
        text += f"{label}\n{price} USD\n\n"
    embed.description = text
    return embed

def build_usd_club():
    embed = discord.Embed(title="🎟️ CLUB FORTNITE (USD)", color=BRAND_COLOR)
    text = ""
    for name, price in CLUB.items():
        text += f"{name}\n{price} USD\n\n"
    embed.description = text
    return embed

def build_converted_embed(moneda, rate):
    embed = discord.Embed(title=f"💱 Precios en {moneda}", color=BRAND_COLOR)
    text = "**🪙 PAVOS**\n\n"
    for name, usd in PAVOS.items():
        price = usd if moneda == "USD" else smart_round(usd * rate)
        label = name
        if "5.000" in name:
            label += " ⭐"
        if "13.500" in name:
            label += " 🔥"
        text += f"{label}\n{price} {moneda}\n\n"

    text += "\n**🎟️ CLUB**\n\n"
    for name, usd in CLUB.items():
        price = usd if moneda == "USD" else smart_round(usd * rate)
        text += f"{name}\n{price} {moneda}\n\n"

    embed.description = text
    embed.set_footer(text="Conversión automática")
    return embed

# =========================
# SELECTOR
# =========================
class CurrencySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=m, emoji="💱") for m in MONEDAS]
        super().__init__(placeholder="Ver precios en tu moneda", options=options)

    async def callback(self, interaction: discord.Interaction):
        moneda = self.values[0]
        rate = 1
        if moneda != "USD":
            rate = await get_rate(moneda)
        embed = build_converted_embed(moneda, rate)
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
# SETUP
# =========================
@bot.tree.command(name="setup", description="Crear canal precios y publicar panel")
async def setup(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    guild = interaction.guild
    channel = discord.utils.get(guild.text_channels, name="precios")

    if not channel:
        channel = await guild.create_text_channel("precios")

    await channel.send(embed=build_usd_pavos())
    await channel.send(embed=build_usd_club())

    selector_embed = discord.Embed(
        title="💱 Ver precios en tu moneda",
        description="Seleccioná tu moneda abajo.",
        color=BRAND_COLOR
    )

    await channel.send(embed=selector_embed, view=CurrencyView())

    await interaction.response.send_message(f"✅ Panel publicado en {channel.mention}", ephemeral=True)

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
# POINTS
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
