import discord
from discord.ext import commands
from discord import app_commands
import json
import time
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
bot = commands.Bot(command_prefix="!", intents=intents)

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
async def setup(interaction: discord.Interaction, canal: discord.TextChannel):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    embed = discord.Embed(
        title="🛒 TIENDA MESSI",
        description="Pavos y Club disponibles\n\nContactá al staff para comprar.",
        color=BRAND_COLOR
    )

    embed.add_field(
        name="🪙 PAVOS",
        value=(
            "• 1.000 Pavos\n"
            "• 2.800 Pavos\n"
            "• 5.000 Pavos ⭐\n"
            "• 13.500 Pavos 🔥"
        ),
        inline=False
    )

    embed.add_field(
        name="🎟️ CLUB FORTNITE",
        value=(
            "• 1 Mes\n"
            "• 3 Meses\n"
            "• 6 Meses"
        ),
        inline=False
    )

    embed.set_footer(text="Messi Store • Sistema automático")

    await canal.send(embed=embed)

    confirm = discord.Embed(
        title="⚙️ Setup completado",
        description=f"Panel publicado en {canal.mention}",
        color=BRAND_COLOR
    )

    await interaction.response.send_message(embed=confirm)

# =========================
# /balance
# =========================
@bot.tree.command(name="balance", description="Ver tu balance")
async def balance(interaction: discord.Interaction):

    data = load_json(BALANCE_FILE)
    balance = data.get(str(interaction.user.id), 0)

    embed = discord.Embed(title="💎 V-BUCKS BALANCE", color=BRAND_COLOR)

    embed.add_field(
        name="👤 Cliente",
        value=interaction.user.mention,
        inline=False
    )

    embed.add_field(
        name="✨ Disponible",
        value=f"**{balance:,} V-Bucks**",
        inline=False
    )

    embed.set_footer(text="Sistema interno de regalos")

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

    if uid not in data:
        data[uid] = 0

    data[uid] += cantidad
    save_json(BALANCE_FILE, data)

    embed = discord.Embed(title="💎 Balance actualizado", color=BRAND_COLOR)

    embed.add_field(name="👤 Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="➕ Agregado", value=f"{cantidad:,} V-Bucks", inline=False)
    embed.add_field(name="✨ Nuevo total", value=f"**{data[uid]:,} V-Bucks**", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# PUNTOS
# =========================
def add_points(user_id, amount):
    data = load_json(POINTS_FILE)
    uid = str(user_id)

    if uid not in data:
        data[uid] = {"total": 0, "history": []}

    data[uid]["total"] += amount
    data[uid]["history"].append({
        "points": amount,
        "timestamp": time.time()
    })

    save_json(POINTS_FILE, data)

def get_points(user_id):
    data = load_json(POINTS_FILE)
    return data.get(str(user_id), {}).get("total", 0)

# =========================
# /points
# =========================
@bot.tree.command(name="points", description="Ver tus puntos")
async def points(interaction: discord.Interaction):

    total = get_points(interaction.user.id)

    if total < 100:
        level = "🥉 Bronce"
    elif total < 300:
        level = "🥈 Plata"
    else:
        level = "🥇 Oro"

    embed = discord.Embed(title="🪙 MESSI REWARDS", color=BRAND_COLOR)

    embed.add_field(name="👤 Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="🪙 Puntos activos", value=f"**{total:,} puntos**", inline=False)
    embed.add_field(name="🏅 Nivel actual", value=level, inline=False)

    embed.set_footer(text="Los puntos vencen automáticamente a los 30 días")

    await interaction.response.send_message(embed=embed)

# =========================
# /addpoints
# =========================
@bot.tree.command(name="addpoints", description="Agregar puntos")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, puntos: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    add_points(usuario.id, puntos)
    total = get_points(usuario.id)

    embed = discord.Embed(title="✨ Puntos acreditados", color=BRAND_COLOR)

    embed.add_field(name="👤 Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="➕ Agregado", value=f"{puntos:,} puntos", inline=False)
    embed.add_field(name="🪙 Total actual", value=f"**{total:,} puntos**", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# /ranks
# =========================
@bot.tree.command(name="ranks", description="Ranking mensual")
async def ranks(interaction: discord.Interaction):

    data = load_json(POINTS_FILE)
    now = time.time()
    ranking = []

    for uid, info in data.items():
        monthly = sum(
            entry["points"]
            for entry in info.get("history", [])
            if now - entry["timestamp"] <= 30 * 86400
        )
        if monthly > 0:
            ranking.append((int(uid), monthly))

    ranking.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆 RANKING MENSUAL",
        description="Clientes con más puntos en los últimos 30 días",
        color=BRAND_COLOR
    )

    medals = ["🥇", "🥈", "🥉"]
    text = ""

    for i, (uid, pts) in enumerate(ranking[:10]):
        medal = medals[i] if i < 3 else "🔹"
        text += f"{medal} <@{uid}> — **{pts:,} pts**\n\n"

    if not text:
        text = "Todavía no hay puntos registrados."

    embed.add_field(name="Tabla mensual", value=text, inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# START
# =========================
bot.run(TOKEN)
