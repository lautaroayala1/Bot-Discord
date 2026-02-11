import discord
from discord import app_commands
from discord.ext import commands
import json
import time
import os

TOKEN = "TU_TOKEN_AQUI"
OWNER_ID = 123456789012345678  # ⚠️ PONÉ TU ID DE DISCORD

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# COLOR MARCA
# =========================
BRAND_COLOR = discord.Color.from_str("#2B0A4D")

# =========================
# ARCHIVOS
# =========================
BALANCE_FILE = "balances.json"
POINTS_FILE = "points.json"

# =========================
# UTILIDADES JSON
# =========================
def load_balances():
    if not os.path.exists(BALANCE_FILE):
        return {}
    with open(BALANCE_FILE, "r") as f:
        return json.load(f)

def save_balances(data):
    with open(BALANCE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_points():
    if not os.path.exists(POINTS_FILE):
        return {}
    with open(POINTS_FILE, "r") as f:
        return json.load(f)

def save_points(data):
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# =========================
# EVENT READY + SYNC GLOBAL
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Conectado como {bot.user}")

# =========================
# /reset (solo Owner)
# =========================
@bot.tree.command(name="reset", description="Sincronizar comandos manualmente")
async def reset(interaction: discord.Interaction):

    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Solo el Owner puede usar esto.", ephemeral=True)

    await bot.tree.sync()

    embed = discord.Embed(
        title="🔄 Comandos actualizados",
        description="Sincronización global completada correctamente.",
        color=BRAND_COLOR
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================
# /balance
# =========================
@bot.tree.command(name="balance", description="Ver balance de regalos")
async def balance(interaction: discord.Interaction):

    data = load_balances()
    user_id = str(interaction.user.id)
    balance = data.get(user_id, 0)

    embed = discord.Embed(
        title="💎 V-BUCKS BALANCE",
        color=BRAND_COLOR
    )

    embed.add_field(
        name="👤 Cliente",
        value=interaction.user.mention,
        inline=False
    )

    embed.add_field(
        name="✨ Disponible",
        value=f"**{balance} V-Bucks**",
        inline=False
    )

    embed.set_footer(text="Sistema interno de regalos")

    await interaction.response.send_message(embed=embed)

# =========================
# /addbalance
# =========================
@bot.tree.command(name="addbalance", description="Agregar balance de regalos")
@app_commands.describe(usuario="Usuario", cantidad="Cantidad")
async def addbalance(interaction: discord.Interaction, usuario: discord.Member, cantidad: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    data = load_balances()
    user_id = str(usuario.id)

    if user_id not in data:
        data[user_id] = 0

    data[user_id] += cantidad
    save_balances(data)

    embed = discord.Embed(
        title="💎 Balance actualizado",
        color=BRAND_COLOR
    )

    embed.add_field(
        name="👤 Cliente",
        value=usuario.mention,
        inline=False
    )

    embed.add_field(
        name="✨ Nuevo balance",
        value=f"**{data[user_id]} V-Bucks**",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

# =========================
# /points
# =========================
@bot.tree.command(name="points", description="Ver puntos Messi Rewards")
async def points(interaction: discord.Interaction):

    data = load_points()
    user_id = str(interaction.user.id)

    total = data.get(user_id, {}).get("total", 0)

    if total < 100:
        level = "🥉 Bronce"
    elif total < 300:
        level = "🥈 Plata"
    else:
        level = "🥇 Oro"

    embed = discord.Embed(
        title="🪙 MESSI REWARDS",
        color=BRAND_COLOR
    )

    embed.add_field(name="👤 Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="🪙 Puntos activos", value=f"**{total} puntos**", inline=False)
    embed.add_field(name="🏅 Nivel actual", value=level, inline=False)

    embed.set_footer(text="Los puntos vencen automáticamente a los 30 días")

    await interaction.response.send_message(embed=embed)

# =========================
# /addpoints
# =========================
@bot.tree.command(name="addpoints", description="Agregar puntos")
@app_commands.describe(usuario="Usuario", puntos="Cantidad de puntos")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, puntos: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)

    data = load_points()
    user_id = str(usuario.id)

    if user_id not in data:
        data[user_id] = {"total": 0, "history": []}

    data[user_id]["total"] += puntos
    data[user_id]["history"].append({
        "points": puntos,
        "timestamp": time.time()
    })

    save_points(data)

    embed = discord.Embed(
        title="✨ Puntos acreditados",
        color=BRAND_COLOR
    )

    embed.add_field(name="👤 Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="➕ Puntos agregados", value=f"**+{puntos}**", inline=False)
    embed.add_field(name="🪙 Total actual", value=f"**{data[user_id]['total']} puntos**", inline=False)

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
        monthly = 0
        for entry in info.get("history", []):
            if now - entry["timestamp"] <= 30 * 86400:
                monthly += entry["points"]

        if monthly > 0:
            ranking.append((int(user_id), monthly))

    ranking.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆 RANKING MENSUAL",
        description="Top clientes últimos 30 días",
        color=BRAND_COLOR
    )

    if not ranking:
        embed.add_field(
            name="Sin datos",
            value="Todavía no hay puntos registrados.",
            inline=False
        )
        return await interaction.response.send_message(embed=embed)

    medals = ["🥇", "🥈", "🥉"]
    text = ""

    for i, (user_id, points) in enumerate(ranking[:10]):
        user = interaction.guild.get_member(user_id)
        if not user:
            continue

        medal = medals[i] if i < 3 else "🔹"
        text += f"{medal} {user.mention} — **{points} pts**\n\n"

    embed.add_field(name="Tabla mensual", value=text, inline=False)

    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
