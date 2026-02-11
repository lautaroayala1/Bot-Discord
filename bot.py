import discord
from discord import app_commands
from discord.ext import commands
import json
import time
import os

OWNER_ID = 1410689876852084897
GUILD_ID = 1434352670230970411  # ID de tu servidor

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

BRAND_COLOR = discord.Color.from_str("#2B0A4D")

BALANCE_FILE = "balances.json"
POINTS_FILE = "points.json"

# =========================
# JSON
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
# READY + SYNC INSTANTÁNEO
# =========================
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Bot listo como {bot.user}")

# =========================
# /reset (solo owner)
# =========================
@bot.tree.command(name="reset", description="Actualizar comandos", guild=discord.Object(id=GUILD_ID))
async def reset(interaction: discord.Interaction):

    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Solo el Owner.", ephemeral=True)

    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

    embed = discord.Embed(
        title="🔄 Comandos sincronizados",
        description="Actualización completada correctamente.",
        color=BRAND_COLOR
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================
# BALANCE
# =========================
@bot.tree.command(name="balance", description="Ver tu balance", guild=discord.Object(id=GUILD_ID))
async def balance(interaction: discord.Interaction):

    data = load_json(BALANCE_FILE)
    user_id = str(interaction.user.id)
    balance = data.get(user_id, 0)

    embed = discord.Embed(title="💎 V-BUCKS BALANCE", color=BRAND_COLOR)
    embed.add_field(name="👤 Cliente", value=interaction.user.mention, inline=False)
    embed.add_field(name="✨ Disponible", value=f"**{balance} V-Bucks**", inline=False)
    embed.set_footer(text="Sistema interno de regalos")

    await interaction.response.send_message(embed=embed)

# =========================
# ADDBALANCE
# =========================
@bot.tree.command(name="addbalance", description="Agregar balance", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(usuario="Usuario", cantidad="Cantidad")
async def addbalance(interaction: discord.Interaction, usuario: discord.Member, cantidad: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo admins.", ephemeral=True)

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
# POINTS
# =========================
@bot.tree.command(name="points", description="Ver tus puntos", guild=discord.Object(id=GUILD_ID))
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
    embed.set_footer(text="Vencen a los 30 días")

    await interaction.response.send_message(embed=embed)

# =========================
# ADDPOINTS
# =========================
@bot.tree.command(name="addpoints", description="Agregar puntos", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(usuario="Usuario", puntos="Cantidad")
async def addpoints(interaction: discord.Interaction, usuario: discord.Member, puntos: int):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo admins.", ephemeral=True)

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
# RANKS
# =========================
@bot.tree.command(name="ranks", description="Ranking mensual", guild=discord.Object(id=GUILD_ID))
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
        user = interaction.guild.get_member(user_id)
        if not user:
            continue
        medal = medals[i] if i < 3 else "🔹"
        text += f"{medal} {user.mention} — **{pts} pts**\n\n"

    if text == "":
        text = "Todavía no hay puntos registrados."

    embed.add_field(name="Tabla", value=text, inline=False)

    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
