import discord
from discord import app_commands
from discord.ext import commands
import json
import time
import os

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")
STAFF_ROLE_NAME = "Staff"
BRAND_COLOR = discord.Color.from_str("#2B0A4D")

BALANCE_FILE = "balances.json"
POINTS_FILE = "points.json"
SETTINGS_FILE = "settings.json"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# JSON UTIL
# =========================
def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# =========================
# READY + SYNC
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot listo como {bot.user}")

# =========================
# CHECK STAFF
# =========================
def is_staff(member):
    role = discord.utils.get(member.guild.roles, name=STAFF_ROLE_NAME)
    return role in member.roles if role else False

# =========================
# /reset
# =========================
@bot.tree.command(name="reset", description="Sincronizar comandos")
async def reset(interaction: discord.Interaction):

    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ Solo Staff.", ephemeral=True)

    await bot.tree.sync()

    embed = discord.Embed(
        title="🔄 Comandos actualizados",
        description="Sincronización completada correctamente.",
        color=BRAND_COLOR
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================
# /setup
# =========================
@bot.tree.command(name="setup", description="Configurar canal de precios")
async def setup(interaction: discord.Interaction, canal: discord.TextChannel):

    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ Solo Staff.", ephemeral=True)

    data = load_json(SETTINGS_FILE)
    data["price_channel"] = canal.id
    save_json(SETTINGS_FILE, data)

    embed = discord.Embed(
        title="⚙️ Canal configurado",
        description=f"Canal de precios: {canal.mention}",
        color=BRAND_COLOR
    )

    await interaction.response.send_message(embed=embed)

# =========================
# /balance
# =========================
@bot.tree.command(name="balance", description="Ver tu balance")
async def balance(interaction: discord.Interaction):

    data = load_json(BALANCE_FILE)
    balance = data.get(str(interaction.user.id), 0)

    embed = discord.Embed(title="💎 V-BUCKS BALANCE", color=BRAND_COLOR)
    embed.add_field(name="👤 Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="✨ Disponible", value=f"**{balance} V-Bucks**", inline=False)
    embed.set_footer(text="Sistema interno de regalos")

    await interaction.response.send_message(embed=embed)

# =========================
# /addbalance
# =========================
@bot.tree.command(name="addbalance", description="Agregar balance")
async def addbalance(interaction: discord.Interaction, usuario: discord.Member, cantidad: int):

    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ Solo Staff.", ephemeral=True)

    data = load_json(BALANCE_FILE)
    user_id = str(usuario.id)

    if user_id not in data:
        data[user_id] = 0

    data[user_id] += cantidad
    save_json(BALANCE_FILE, data)

    embed = discord.Embed(title="💎 Balance actualizado", color=BRAND_COLOR)
    embed.add_field(name="👤 Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="✨ Nuevo balance", value=f"**{data[user_id]} V-Bucks**", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# /points
# =========================
@bot.tree.command(name="points", description="Ver tus puntos")
async def points(interaction: discord.Interaction):

    data = load_json(POINTS_FILE)
    user_id = str(interaction.user.id)

    total = data.get(user_id, {}).get("total", 0)

    if total < 100:
        level = "🥉 Bronce"
    elif total < 300:
        level = "🥈 Plata"
    else:
        level = "🥇 Oro"

    embed = discord.Embed(title="🪙 MESSI REWARDS", color=BRAND_COLOR)
    embed.add_field(name="👤 Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="🪙 Puntos activos", value=f"**{total} puntos**", inline=False)
    embed.add_field(name="🏅 Nivel", value=level, inline=False)
    embed.set_footer(text="Vencen automáticamente a los 30 días")

    await interaction.response.send_message(embed=embed)

# =========================
# /addpoints
# =========================
@bot.tree.command(name="addpoints", description="Agregar puntos")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, puntos: int):

    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ Solo Staff.", ephemeral=True)

    data = load_json(POINTS_FILE)
    user_id = str(usuario.id)

    if user_id not in data:
        data[user_id] = {"total": 0, "history": []}

    data[user_id]["total"] += puntos
    data[user_id]["history"].append({
        "points": puntos,
        "timestamp": time.time()
    })

    save_json(POINTS_FILE, data)

    embed = discord.Embed(title="✨ Puntos acreditados", color=BRAND_COLOR)
    embed.add_field(name="👤 Cliente", value=usuario.mention, inline=False)
    embed.add_field(name="➕ Agregado", value=f"**+{puntos} puntos**", inline=False)
    embed.add_field(name="🪙 Total actual", value=f"**{data[user_id]['total']}**", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# /ranks
# =========================
@bot.tree.command(name="ranks", description="Ranking mensual")
async def ranks(interaction: discord.Interaction):

    data = load_json(POINTS_FILE)
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

    embed = discord.Embed(
        title="🏆 RANKING MENSUAL",
        description="Top clientes últimos 30 días",
        color=BRAND_COLOR
    )

    medals = ["🥇", "🥈", "🥉"]
    text = ""

    for i, (user_id, pts) in enumerate(ranking[:10]):
        member = interaction.guild.get_member(user_id)
        if not member:
            continue
        medal = medals[i] if i < 3 else "🔹"
        text += f"{medal} {member.mention} — **{pts} pts**\n\n"

    if text == "":
        text = "Todavía no hay puntos registrados."

    embed.add_field(name="Tabla mensual", value=text, inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# START
# =========================
bot.run(TOKEN)
