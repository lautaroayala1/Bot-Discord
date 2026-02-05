import os
import discord
from discord.ext import commands
import aiohttp
import time
import math
import json
from pathlib import Path

# =========================
# TOKEN (RAILWAY)
# =========================
TOKEN = os.getenv("TOKEN")

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

# =========================
# MONEDAS
# =========================
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

EMOJIS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "ARS": "🇦🇷",
    "CLP": "🇨🇱",
    "PEN": "🇵🇪",
    "COP": "🇨🇴",
    "BRL": "🇧🇷",
    "MXN": "🇲🇽",
}

# =========================
# BALANCES (V-BUCKS)
# =========================
BALANCE_FILE = Path("balances.json")

if not BALANCE_FILE.exists():
    BALANCE_FILE.write_text("{}")

def load_balances():
    return json.loads(BALANCE_FILE.read_text())

def save_balances(data):
    BALANCE_FILE.write_text(json.dumps(data, indent=2))

def get_balance(user_id: int) -> int:
    return load_balances().get(str(user_id), 0)

def set_balance(user_id: int, amount: int):
    data = load_balances()
    data[str(user_id)] = max(int(amount), 0)
    save_balances(data)

# =========================
# PERMISOS STAFF / OWNER
# =========================
def is_staff_or_owner(interaction: discord.Interaction) -> bool:
    allowed = {"staff", "owner"}
    roles = {r.name.lower() for r in interaction.user.roles}
    return not allowed.isdisjoint(roles)

# =========================
# SELECTOR DE MONEDAS
# =========================
class CurrencySelect(discord.ui.Select):
    def __init__(self, precios, titulo, emoji):
        self.precios = precios
        self.titulo = titulo
        self.emoji = emoji

        options = [
            discord.SelectOption(
                label=MONEDAS[c],
                value=c,
                emoji=EMOJIS[c]
            ) for c in MONEDAS
        ]

        super().__init__(
            placeholder="💱 Elegí tu moneda",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        moneda = self.values[0]
        rate = 1 if moneda == "USD" else await get_rate(moneda)

        embed = discord.Embed(
            title=f"{self.emoji} {self.titulo}",
            description="💎 **Precios finales**",
            color=discord.Color.gold()
        )

        for nombre, usd in self.precios.items():
            valor = usd * rate

            # 🔑 EUR NO SE REDONDEA
            if moneda not in ("USD", "EUR"):
                valor = smart_round(valor)

            embed.add_field(
                name=nombre,
                value=f"✨ **{valor:,.2f} {moneda}**" if moneda == "EUR" else f"✨ **{valor:,.0f} {moneda}**",
                inline=False
            )

        embed.set_footer(text="Base USD · Conversión automática")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CurrencyView(discord.ui.View):
    def __init__(self, precios, titulo, emoji):
        super().__init__(timeout=None)
        self.add_item(CurrencySelect(precios, titulo, emoji))

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Conectado como {bot.user}")

# =========================
# /setup
# =========================
@bot.tree.command(name="setup", description="Configura el canal 💰┃precios")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):

    guild = interaction.guild
    canal = discord.utils.get(guild.text_channels, name="💰┃precios")
    if not canal:
        canal = await guild.create_text_channel("💰┃precios")

    embed_pavos = discord.Embed(
        title="🪙 PAVOS DE FORTNITE",
        description=(
            "🎮 **Recargá pavos de forma segura**\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🪙 1.000 Pavos — US$6\n"
            "🪙 2.800 Pavos — US$15\n"
            "🪙 5.000 Pavos — US$28\n"
            "🪙 13.500 Pavos — US$42\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⬇️ *Elegí tu moneda abajo*"
        ),
        color=discord.Color.gold()
    )

    await canal.send(embed=embed_pavos, view=CurrencyView(PAVOS, "Pavos Fortnite", "🪙"))
    await canal.send("\u200b")

    embed_club = discord.Embed(
        title="🎟️ CLUB DE FORTNITE",
        description=(
            "👑 **Beneficios exclusivos todos los meses**\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🎟️ 1 mes — US$3\n"
            "🎟️ 3 meses — US$9\n"
            "🎟️ 6 meses — US$15\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⬇️ *Elegí tu moneda abajo*"
        ),
        color=discord.Color.gold()
    )

    await canal.send(embed=embed_club, view=CurrencyView(CLUB, "Club de Fortnite", "🎟️"))

    await interaction.response.send_message(
        "✨ **Canal 💰┃precios configurado correctamente**",
        ephemeral=True
    )

# =========================
# /balance (V-BUCKS)
# =========================
@bot.tree.command(name="balance", description="Muestra tu V-Bucks balance")
async def balance(interaction: discord.Interaction, usuario: discord.Member | None = None):

    target = usuario or interaction.user
    saldo = get_balance(target.id)

    embed = discord.Embed(
        title=":Pavos: **V-BUCKS BALANCE**",
        description=(
            f"👤 **Usuario:** {target.mention}\n\n"
            f":Pavos: **Balance disponible:**\n"
            f"✨ **{saldo:,} V-Bucks** para regalos"
        ),
        color=discord.Color.gold()
    )

    embed.set_footer(text="Balance interno · Sistema de regalos")
    await interaction.response.send_message(embed=embed)

# =========================
# /addbalance
# =========================
@bot.tree.command(name="addbalance", description="Agrega V-Bucks balance a un usuario")
async def addbalance(interaction: discord.Interaction, usuario: discord.Member, monto: int):

    if not is_staff_or_owner(interaction):
        return await interaction.response.send_message(
            "⛔ No tenés permisos para usar este comando.",
            ephemeral=True
        )

    nuevo = get_balance(usuario.id) + monto
    set_balance(usuario.id, nuevo)

    embed = discord.Embed(
        title=":Pavos: **BALANCE ACREDITADO**",
        description=(
            f"👤 **Usuario:** {usuario.mention}\n"
            f":Pavos: **Pavos agregados:** {monto:,}\n\n"
            f"✨ **Nuevo balance:**\n"
            f":Pavos: **{nuevo:,} V-Bucks**"
        ),
        color=discord.Color.gold()
    )

    embed.set_footer(text=f"Acreditado por {interaction.user}")
    await interaction.response.send_message(embed=embed)

# =========================
# /removebalance
# =========================
@bot.tree.command(name="removebalance", description="Quita V-Bucks balance a un usuario")
async def removebalance(interaction: discord.Interaction, usuario: discord.Member, monto: int):

    if not is_staff_or_owner(interaction):
        return await interaction.response.send_message(
            "⛔ No tenés permisos para usar este comando.",
            ephemeral=True
        )

    actual = get_balance(usuario.id)
    nuevo = max(actual - monto, 0)
    set_balance(usuario.id, nuevo)

    embed = discord.Embed(
        title=":Pavos: **BALANCE DESCONTADO**",
        description=(
            f"👤 **Usuario:** {usuario.mention}\n"
            f":Pavos: **Pavos descontados:** {monto:,}\n\n"
            f"✨ **Balance restante:**\n"
            f":Pavos: **{nuevo:,} V-Bucks**"
        ),
        color=discord.Color.gold()
    )

    embed.set_footer(text=f"Operación realizada por {interaction.user}")
    await interaction.response.send_message(embed=embed)

# =========================
# RUN
# =========================
bot.run(TOKEN)
