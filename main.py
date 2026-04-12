import os
import re
import asyncio
import random
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
import aiohttp
import time
import math
import json
from pathlib import Path

# =========================
# CONFIG DESDE VARIABLES DE ENTORNO (RAILWAY)
# =========================
def get_env(*names: str, default: str | None = None, required: bool = False) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    if default is not None:
        return default.strip() if isinstance(default, str) else default
    if required:
        joined = ", ".join(names)
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {joined}")
    return ""


def get_env_int(*names: str, default: int = 0) -> int:
    for name in names:
        value = os.getenv(name)
        if value is None or value.strip() == "":
            continue
        try:
            return int(value.strip())
        except ValueError:
            raise RuntimeError(f"La variable {name} debe ser numérica. Valor recibido: {value!r}")
    return default


TOKEN = get_env("DISCORD_BOT_TOKEN", "TOKEN", required=True)

# =========================
# EMOJI CUSTOM
# =========================
PAVOS_EMOJI = get_env("PAVOS_EMOJI", default="<:Pavos:1440841778373722213>")

# ── EMOJIS CUSTOM PARA VENTAS ──
# Reemplazá los IDs por los reales de tu servidor
PIXEL_HEART_EMOJI = get_env("PIXEL_HEART_EMOJI", default="<a:pixelheart:0000000000000000000>")
BLUE_ARROW_EMOJI = get_env("BLUE_ARROW_EMOJI", default="<a:bluearrow:0000000000000000000>")

# ── ADJETIVOS ALEATORIOS PARA VENTAS ──
SALE_ADJECTIVES = [
    "Genio",
    "Crack",
    "Millonario",
    "Exitoso",
    "Grande",
    "Caballero",
    "Guapo",
    "Amado",
    "Apreciado",
    "Máquina",
    "Leyenda",
    "Campeón",
    "Maestro",
    "Fenómeno",
    "Titan",
    "Jefe",
    "Rey",
    "Héroe",
    "Crack Total",
    "Duro",
    "Bestia",
    "Figura",
    "Monstruo",
    "Top",
    "Querido",
    "Elegante",
    "Distinguido",
    "Admirado",
    "Respetado",
    "Brillante",
]

# =========================
# EMBED COLOR (CELESTE)
# =========================
EMBED_COLOR = discord.Color.from_rgb(25, 181, 255)  # #19B5FF

# Color para la barra lateral del embed de ventas (morado como en la imagen)
SALES_EMBED_COLOR = discord.Color.from_rgb(155, 89, 182)  # Morado


# =========================
# LINKS / CANALES
# =========================
WEBSITE_URL = get_env("WEBSITE_URL", default="https://vortexggshop.mysellauth.com/")
VOUCHES_CHANNEL_ID = get_env_int("VOUCHES_CHANNEL_ID", default=1434701785284739224)

# =========================
# SELLAUTH CONFIG
# =========================
SELLAUTH_API_KEY = get_env("SELLAUTH_API_KEY", required=True)
SELLAUTH_SHOP_ID = get_env("SELLAUTH_SHOP_ID", required=True)
SELLAUTH_BASE_URL = get_env("SELLAUTH_BASE_URL", default="https://api.sellauth.com/v1")
SALES_LOG_CHANNEL_NAME = get_env("SALES_LOG_CHANNEL_NAME", default="📦┃ventas-logs")
RESTOCK_CHANNEL_NAME = get_env("RESTOCK_CHANNEL_NAME", default="📦┃stock")
RESTOCK_POLL_MINUTES = get_env_int("RESTOCK_POLL_MINUTES", default=1)

# ── NOMBRE DE LA TIENDA (para el mensaje de ventas) ──
SHOP_NAME = get_env("SHOP_NAME", default="VortexGGShop")

# =========================
# BOT (SLASH ONLY)
# =========================
INTENTS = discord.Intents.default()
INTENTS.members = True   # Necesario para leer roles en interacciones

bot = commands.Bot(
    command_prefix="!",   # prefix dummy — los slash commands no lo usan
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
    "🪙 5.000 Pavos": 25,
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
# VOUCHES (CONTADOR REAL + NUMERACIÓN)
# =========================
VOUCH_COUNTER_FILE = Path("vouch_counter.json")
if not VOUCH_COUNTER_FILE.exists():
    VOUCH_COUNTER_FILE.write_text(json.dumps({"last": 0}, indent=2))

VOUCH_LOCK = asyncio.Lock()

def _load_vouch_last() -> int:
    try:
        data = json.loads(VOUCH_COUNTER_FILE.read_text())
        return int(data.get("last", 0))
    except Exception:
        return 0

def _save_vouch_last(last: int):
    VOUCH_COUNTER_FILE.write_text(json.dumps({"last": int(last)}, indent=2))

async def _count_messages_in_channel(channel: discord.abc.Messageable) -> int:
    count = 0
    async for _ in channel.history(limit=None):
        count += 1
    return count

async def _get_next_vouch_number(channel: discord.abc.Messageable) -> int:
    async with VOUCH_LOCK:
        last = _load_vouch_last()
        if last <= 0:
            last = await _count_messages_in_channel(channel)
        last += 1
        _save_vouch_last(last)
        return last

# =========================
# PERMISOS STAFF / OWNER
# =========================
def is_staff_or_owner(interaction: discord.Interaction) -> bool:
    allowed = {"staff", "owner"}
    roles = {r.name.lower() for r in interaction.user.roles}
    return not allowed.isdisjoint(roles)


def is_staff_or_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    roles = {r.name.lower() for r in getattr(interaction.user, "roles", [])}
    return "staff" in roles

def is_staff_only(interaction: discord.Interaction) -> bool:
    roles = {r.name.lower() for r in getattr(interaction.user, "roles", [])}
    return "staff" in roles

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
            color=EMBED_COLOR
        )

        for nombre, usd in self.precios.items():
            valor = usd * rate

            if moneda not in ("USD", "EUR"):
                valor = smart_round(valor)

            texto = (
                f"✨ **{valor:,.2f} {moneda}**"
                if moneda == "EUR"
                else f"✨ **{valor:,.0f} {moneda}**"
            )

            embed.add_field(
                name=nombre,
                value=texto,
                inline=False
            )

        embed.set_footer(text="Base USD · Conversión automática")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CurrencyView(discord.ui.View):
    def __init__(self, precios, titulo, emoji):
        super().__init__(timeout=120)
        self.add_item(CurrencySelect(precios, titulo, emoji))


# =========================
# CATALOGO PRODUCTOS (BASE USD)
# =========================
PRODUCT_CATALOG = {
    "rl": {
        "title": "🪙 ROCKET LEAGUE CREDITS",
        "subtitle": "🎮 Recargá créditos más barato que la tienda oficial",
        "note": "📌 Solo si sos de **Xbox** (o entramos desde nuestra Xbox, compramos lo que querés con los créditos y salimos de la cuenta).",
        "sections": [
            ("", [
                ("🪙 500 Credits", 4.00, ""),
                ("🪙 1.100 Credits", 8.00, "⭐ Más elegido"),
                ("🪙 3.000 Credits", 20.00, ""),
                ("🪙 6.500 Credits", 40.00, "🔥 Mejor valor"),
            ])
        ],
        "bullets": [
            "💸 Hasta 20% más barato que la tienda oficial",
            "✔ Entrega rápida",
            "✔ Método seguro",
            "✔ Soporte activo",
        ],
    },
    "cod": {
        "title": "🪙 CALL OF DUTY POINTS",
        "subtitle": "🎮 Recargá puntos más barato que la tienda oficial",
        "note": "📌 Solo si sos de **Xbox** (o entramos desde nuestra Xbox, compramos lo que querés con los créditos y salimos de la cuenta).",
        "sections": [
            ("", [
                ("🪙 200 CP", 1.80, ""),
                ("🪙 500 CP", 4.00, ""),
                ("🪙 1.100 CP", 8.50, "⭐ Más elegido"),
                ("🪙 2.400 CP", 17.00, ""),
                ("🪙 5.000 CP", 34.00, ""),
                ("🪙 13.000 CP", 85.00, "🔥 Mejor valor"),
            ])
        ],
        "bullets": [
            "💸 Hasta 20% más barato que la tienda oficial",
            "✔ Entrega rápida",
            "✔ Método seguro",
            "✔ Soporte activo",
        ],
    },
    "gamepass": {
        "title": "🎮 XBOX GAME PASS",
        "subtitle": "",
        "note": "",
        "sections": [
            ("🎮 Core", [
                ("1 mes", 7.50, ""),
                ("3 meses", 20.00, ""),
                ("12 meses", 70.00, ""),
            ]),
            ("🔥 Ultimate", [
                ("1 mes", 13.50, "⭐"),
                ("3 meses", 38.00, ""),
                ("12 meses", 140.00, "🔥"),
            ]),
        ],
        "bullets": [
            "✔ Más barato que tienda oficial",
            "✔ Activación rápida",
            "✔ Soporte activo",
        ],
    },
    "fc26": {
        "title": "⚽ FC 26 POINTS",
        "subtitle": "",
        "note": "📌 Solo si sos de **Xbox**.",
        "sections": [
            ("", [
                ("🟢 100 Points", 0.95, ""),
                ("🟢 500 Points", 4.50, ""),
                ("🟢 1.050 Points", 8.90, "⭐ Más elegido"),
                ("🟢 1.600 Points", 13.50, ""),
                ("🟢 2.800 Points", 22.00, ""),
                ("🟢 5.900 Points", 44.00, ""),
                ("🟢 12.000 Points", 88.00, ""),
                ("🟢 18.500 Points", 135.00, "🔥 Mejor valor"),
            ])
        ],
        "bullets": [],
    },
}

def _fmt_money(usd: float, moneda: str, rate: float) -> str:
    val = usd * rate
    if moneda == "USD":
        return f"US${val:,.2f}"
    if moneda == "EUR":
        return f"{val:,.2f} EUR"
    val = smart_round(val)
    return f"{val:,.0f} {moneda}"

def build_product_embed(product_id: str, moneda: str, rate: float) -> discord.Embed:
    info = PRODUCT_CATALOG.get(product_id)
    if not info:
        return discord.Embed(
            title="⛔ Producto no encontrado",
            description="Probá de nuevo desde el menú.",
            color=EMBED_COLOR
        )

    embed = discord.Embed(
        title=info["title"],
        color=EMBED_COLOR
    )

    parts = []

    if info.get("subtitle"):
        parts.append(info["subtitle"])

    if info.get("note"):
        parts.append(info["note"])

    parts.append("━━━━━━━━━━━━━━━━━━")

    for section_title, items in info.get("sections", []):
        if section_title:
            parts.append(f"**{section_title}**")
        for label, usd, badge in items:
            precio = _fmt_money(usd, moneda, rate)
            suf = f" {badge}" if badge else ""
            parts.append(f"{label} — {precio}{suf}")
        parts.append("")

    parts.append("━━━━━━━━━━━━━━━━━━")

    for b in info.get("bullets", []):
        parts.append(b)

    parts.append("")
    parts.append("⬇️ *Elegí tu moneda abajo*")

    embed.description = "\n".join([p for p in parts if p != ""])
    embed.set_footer(text="Base USD · Conversión automática")
    return embed

class ProductCurrencySelect(discord.ui.Select):
    def __init__(self, product_id: str):
        self.product_id = product_id
        options = [
            discord.SelectOption(label=MONEDAS[c], value=c, emoji=EMOJIS[c])
            for c in MONEDAS
        ]
        super().__init__(
            placeholder="💱 Seleccioná tu moneda",
            options=options,
            custom_id=f"product_currency_select:{product_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        moneda = self.values[0]
        rate = 1 if moneda == "USD" else await get_rate(moneda)
        embed = build_product_embed(self.product_id, moneda, rate)
        await interaction.response.edit_message(embed=embed, view=self.view)

class ProductCurrencyView(discord.ui.View):
    def __init__(self, product_id: str):
        super().__init__(timeout=None)
        self.add_item(ProductCurrencySelect(product_id))

async def create_ticket_channel(guild: discord.Guild, user: discord.Member, game_name: str) -> discord.TextChannel:
    category = discord.utils.get(guild.categories, name="tickets")
    if not category:
        category = await guild.create_category("tickets")

    base_name = f"ticket-{user.name}".lower().replace(" ", "-")
    name = base_name
    i = 2
    while discord.utils.get(guild.text_channels, name=name):
        name = f"{base_name}-{i}"
        i += 1

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }

    staff_role = next((r for r in guild.roles if r.name.lower() == "staff"), None)
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    canal = await guild.create_text_channel(name=name, category=category, overwrites=overwrites)

    staff_ping = staff_role.mention if staff_role else "@here"
    embed = discord.Embed(
        title="🎮 Consulta de juego",
        description=(
            f"👤 Cliente: {user.mention}\n"
            f"🎯 Juego: **{game_name}**\n\n"
            "📌 *Solo Xbox o juegos de PC que estén en Microsoft Store.*"
        ),
        color=EMBED_COLOR
    )

    await canal.send(content=staff_ping, embed=embed)
    return canal

class GameSearchModal(discord.ui.Modal, title="🎮 Consulta de juego"):
    juego = discord.ui.TextInput(
        label="¿Qué juego buscás?",
        placeholder="Ej: EA SPORTS FC 26 / Forza / etc",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("⛔ Este formulario solo funciona dentro de un servidor.", ephemeral=True)

        canal = await create_ticket_channel(interaction.guild, interaction.user, str(self.juego))
        await interaction.response.send_message(f"✅ Listo. Te abrí un ticket: {canal.mention}", ephemeral=True)

class ConsultaProductoSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Créditos Rocket League",
                value="rl",
                description="Solo Xbox / desde nuestra Xbox",
                emoji="🪙"
            ),
            discord.SelectOption(
                label="Call of Duty Points",
                value="cod",
                description="Solo Xbox / desde nuestra Xbox",
                emoji="🎮"
            ),
            discord.SelectOption(
                label="Xbox Game Pass",
                value="gamepass",
                description="Core y Ultimate",
                emoji="🎟️"
            ),
            discord.SelectOption(
                label="Juegos (Microsoft Store)",
                value="games",
                description="Abrir ticket para cotizar",
                emoji="📝"
            ),
            discord.SelectOption(
                label="FC 26 Points",
                value="fc26",
                description="Solo Xbox",
                emoji="⚽"
            ),
        ]
        super().__init__(
            placeholder="📦 Elegí un producto",
            options=options,
            custom_id="consulta_producto_select"
        )

    async def callback(self, interaction: discord.Interaction):
        product_id = self.values[0]

        if product_id == "games":
            return await interaction.response.send_modal(GameSearchModal())

        embed = build_product_embed(product_id, "USD", 1.0)
        view = ProductCurrencyView(product_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConsultaProductoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ConsultaProductoSelect())

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    bot.add_view(ConsultaProductoView())
    bot.add_view(PreciosProductView())
    for pk in FULL_PRICE_CATALOG:
        bot.add_view(PreciosCurrencyView(pk))
    if not sales