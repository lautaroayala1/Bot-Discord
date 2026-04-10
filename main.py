import os
import re
import asyncio
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

# =========================
# EMBED COLOR (CELESTE)
# =========================
EMBED_COLOR = discord.Color.from_rgb(25, 181, 255)  # #19B5FF


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
        # Si nunca se inicializó, lo sincronizamos 1 vez con el conteo real.
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
    # Admin o rol llamado "Staff"
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

            # EUR NO SE REDONDEA
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
# CONSULTA POR PRODUCTO
# =========================
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
    # Views persistentes (registrar antes del sync)
    bot.add_view(ConsultaProductoView())
    bot.add_view(PreciosProductView())
    for pk in FULL_PRICE_CATALOG:
        bot.add_view(PreciosCurrencyView(pk))
    # Iniciar tarea de ventas
    if not sales_log_task.is_running():
        sales_log_task.start()
    # Iniciar tarea de restock
    if not restock_poll_task.is_running():
        restock_poll_task.start()
    print(f"✅ Conectado como {bot.user}")
    # Sync de slash commands en background para no bloquear el heartbeat
    asyncio.create_task(_sync_commands())

async def _sync_commands():
    try:
        await bot.tree.sync()
        print("✅ Slash commands sincronizados.")
    except Exception as e:
        print(f"⚠️ Error sincronizando comandos: {e}")

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
            "🪙 5.000 Pavos — US$25\n"
            "🪙 13.500 Pavos — US$42\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⬇️ *Elegí tu moneda abajo*"
        ),
        color=EMBED_COLOR
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
        color=EMBED_COLOR
    )

    await canal.send(embed=embed_club, view=CurrencyView(CLUB, "Club de Fortnite", "🎟️"))


    embed_consulta = discord.Embed(
        title="🛒 LISTA DE PRECIOS — VORTEXGGSHOP",
        description=(
            "Seleccioná un producto del menú desplegable para ver los precios detallados.\n"
            "También podés cambiar la moneda a la tuya 💱\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🎮 **FORTNITE:** Pavos, Club\n"
            "🕹️ **JUEGOS:** Valorant, COD Points, Xbox Game Pass\n"
            "📺 **STREAMING:** Spotify, Netflix, Prime, Crunchyroll, HBO, DAZN, Disney+\n"
            "🧠 **IA & HERRAMIENTAS:** ChatGPT Plus, Gemini Pro+, Adobe CC\n"
            "🎨 **DISEÑO & EDICIÓN:** CapCut Pro, Canva Pro\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⬇️ *Usá el menú de abajo para ver precios*"
        ),
        color=EMBED_COLOR
    )

    await canal.send("\u200b")
    await canal.send(embed=embed_consulta, view=PreciosProductView())

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
        title=f"{PAVOS_EMOJI} **V-BUCKS BALANCE**",
        description=(
            f"👤 **Usuario:** {target.mention}\n\n"
            f"{PAVOS_EMOJI} **Balance disponible:**\n"
            f"✨ **{saldo:,} V-Bucks** para regalos"
        ),
        color=EMBED_COLOR
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
        title=f"{PAVOS_EMOJI} **BALANCE ACREDITADO**",
        description=(
            f"👤 **Usuario:** {usuario.mention}\n"
            f"{PAVOS_EMOJI} **Pavos agregados:** {monto:,}\n\n"
            f"✨ **Nuevo balance:**\n"
            f"{PAVOS_EMOJI} **{nuevo:,} V-Bucks**"
        ),
        color=EMBED_COLOR
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
        title=f"{PAVOS_EMOJI} **BALANCE DESCONTADO**",
        description=(
            f"👤 **Usuario:** {usuario.mention}\n"
            f"{PAVOS_EMOJI} **Pavos descontados:** {monto:,}\n\n"
            f"✨ **Balance restante:**\n"
            f"{PAVOS_EMOJI} **{nuevo:,} V-Bucks**"
        ),
        color=EMBED_COLOR
    )

    embed.set_footer(text=f"Operación realizada por {interaction.user}")
    await interaction.response.send_message(embed=embed)

# =========================
# /balances (STAFF / ADMIN)
# =========================
@bot.tree.command(name="balances", description="Muestra todos los balances (solo Staff/Admin)")
async def balances(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True)

    if not is_staff_or_admin(interaction):
        return await interaction.response.send_message("⛔ No tenés permisos para usar este comando.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    data = load_balances()

    entries: list[tuple[discord.Member, int]] = []
    for uid_str, amount in data.items():
        try:
            uid = int(uid_str)
            amount = int(amount)
        except Exception:
            continue

        # Solo mostramos miembros que estén en este servidor
        member = interaction.guild.get_member(uid)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(uid)
            except Exception:
                member = None

        if member is None:
            continue

        entries.append((member, max(amount, 0)))

    if not entries:
        return await interaction.followup.send("📭 No hay balances guardados para miembros de este servidor.", ephemeral=True)

    entries.sort(key=lambda x: x[1], reverse=True)

    # Armamos embeds en partes si es muy largo
    lines = [f"• {m.mention} — **{amt:,} V-Bucks**" for m, amt in entries]

    embeds: list[discord.Embed] = []
    chunk: list[str] = []
    size = 0
    for line in lines:
        # +1 por salto de línea
        if size + len(line) + 1 > 3800:
            embeds.append(discord.Embed(
                title=f"{PAVOS_EMOJI} BALANCES DEL SERVIDOR",
                description="\n".join(chunk),
                color=EMBED_COLOR
            ))
            chunk = []
            size = 0
        chunk.append(line)
        size += len(line) + 1

    if chunk:
        embeds.append(discord.Embed(
            title=f"{PAVOS_EMOJI} BALANCES DEL SERVIDOR",
            description="\n".join(chunk),
            color=EMBED_COLOR
        ))

    total_users = len(entries)
    total_balance = sum(a for _, a in entries)
    for e in embeds:
        e.set_footer(text=f"Usuarios: {total_users} · Total: {total_balance:,} V-Bucks")

    await interaction.followup.send(embed=embeds[0], ephemeral=True)
    for e in embeds[1:]:
        await interaction.followup.send(embed=e, ephemeral=True)

# =========================
# /website
# =========================
class WebsiteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(discord.ui.Button(label="Abrir website", url=WEBSITE_URL))

@bot.tree.command(name="website", description="Link del website")
async def website(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌐 Website",
        description=f"{WEBSITE_URL}",
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed, view=WebsiteView(), ephemeral=True)

# =========================
# /vouchescount (CONTEO REAL)
# =========================
@bot.tree.command(name="vouchescount", description="Cuenta la cantidad real de vouches del canal")
async def vouchescount(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    channel = bot.get_channel(VOUCHES_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(VOUCHES_CHANNEL_ID)
        except Exception:
            channel = None

    if channel is None:
        return await interaction.followup.send("⛔ No pude encontrar el canal de vouches.", ephemeral=True)

    try:
        count = await _count_messages_in_channel(channel)
    except Exception as e:
        return await interaction.followup.send(f"⛔ Error contando mensajes: {e}", ephemeral=True)

    embed = discord.Embed(
        title="🧾 Vouches count",
        description=f"En <#{VOUCHES_CHANNEL_ID}> hay **{count}** vouches.",
        color=EMBED_COLOR
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

# =========================
# /vouch (EMBED COMO LA FOTO)
# =========================
@bot.tree.command(name="vouch", description="Dejá tu vouch (producto + opinión + imagen opcional)")
async def vouch(
    interaction: discord.Interaction,
    producto: str,
    opinion: str,
    estrellas: discord.app_commands.Range[int, 1, 5] = 5,
    imagen: discord.Attachment | None = None
):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True)

    # Validar que el adjunto sea una imagen (si se mandó uno)
    if imagen is not None:
        allowed = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")
        if imagen.content_type not in allowed:
            return await interaction.response.send_message(
                "⛔ Solo se permiten imágenes (PNG, JPG, GIF, WEBP).",
                ephemeral=True
            )

    await interaction.response.defer(ephemeral=True)

    channel = bot.get_channel(VOUCHES_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(VOUCHES_CHANNEL_ID)
        except Exception:
            channel = None

    if channel is None:
        return await interaction.followup.send("⛔ No pude encontrar el canal de vouches.", ephemeral=True)

    # Número de vouch (persistente). Si es la primera vez, se sincroniza 1 vez con el conteo real.
    vouch_no = await _get_next_vouch_number(channel)

    stars = "⭐" * int(estrellas)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    embed = discord.Embed(
        title="Thank you for your vouch!",
        description=stars,
        color=EMBED_COLOR
    )

    embed.add_field(
        name="Vouch:",
        value=f"**Producto:** {producto}\n**Opinión:** {opinion}",
        inline=False
    )

    embed.add_field(name="Vouch N°:", value=str(vouch_no), inline=True)
    embed.add_field(name="Vouched by:", value=interaction.user.mention, inline=True)
    embed.add_field(name="Vouched at:", value=now_str, inline=True)

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="VortexGGShop")

    # Si el usuario adjuntó una imagen, la mostramos en el embed
    if imagen is not None:
        embed.set_image(url=imagen.url)

    await channel.send(embed=embed)
    await interaction.followup.send(f"✅ Vouch enviado en <#{VOUCHES_CHANNEL_ID}>.", ephemeral=True)
# =========================
# CATALOGO COMPLETO DE PRECIOS
# =========================
FULL_PRICE_CATALOG = {
    # ── FORTNITE ────────────────────────────────────────────────
    "fortnite_pavos": {
        "label": "🪙 Pavos (V-Bucks)",
        "category": "fortnite",
        "emoji": "🪙",
        "title": "🪙 PAVOS (V-BUCKS) — FORTNITE",
        "description": "🎮 Recargá pavos más baratos que la tienda oficial.\n💳 Entrega rápida · Método seguro · Soporte activo",
        "items": [
            ("1.000 Pavos",  6.00,  ""),
            ("2.800 Pavos",  15.00, "⭐ Más elegido"),
            ("5.000 Pavos",  25.00, "🔥 Mejor precio"),
            ("13.500 Pavos", 42.00, "💎 Mejor valor"),
        ],
    },
    "fortnite_crew": {
        "label": "🎟️ Fortnite Club (Crew)",
        "category": "fortnite",
        "emoji": "🎟️",
        "title": "🎟️ FORTNITE CREW — CLUB",
        "description": "👑 Beneficios exclusivos todos los meses: skin, pavos y Battle Pass incluido.",
        "items": [
            ("Club 1 Mes",   3.00,  ""),
            ("Club 3 Meses", 9.00,  "⭐ Más elegido"),
            ("Club 6 Meses", 15.00, "💎 Mejor precio"),
        ],
    },
    # ── JUEGOS ──────────────────────────────────────────────────
    "valorant": {
        "label": "⚔️ Valorant — Cuenta",
        "category": "juegos",
        "emoji": "⚔️",
        "title": "⚔️ VALORANT — CUENTA",
        "description": "🎮 Cuenta de Valorant al mejor precio del mercado.\n⚡ Entrega inmediata tras el pago.",
        "items": [
            ("Cuenta Valorant", 10.00, "🔥 OFERTA (antes $15)"),
        ],
    },
    "cod_points": {
        "label": "🔫 COD Points",
        "category": "juegos",
        "emoji": "🔫",
        "title": "🔫 COD POINTS — CALL OF DUTY",
        "description": "🎮 Recargá COD Points más baratos que la tienda oficial.\n📌 Solo Xbox.",
        "items": [
            ("4.800 CP",  24.99, ""),
            ("9.600 CP",  39.99, "⭐ Más elegido"),
            ("14.400 CP", 59.99, "💎 Mejor valor"),
        ],
    },
    "xbox_gamepass": {
        "label": "🎮 Xbox Game Pass Premium",
        "category": "juegos",
        "emoji": "🎮",
        "title": "🎮 XBOX GAME PASS PREMIUM",
        "description": "🕹️ Accedé a cientos de juegos por un precio increíble.\n✔ Activación rápida · Soporte activo",
        "items": [
            ("Game Pass Premium", 4.00, ""),
        ],
    },
    # ── STREAMING ───────────────────────────────────────────────
    "spotify": {
        "label": "🎵 Spotify Premium",
        "category": "streaming",
        "emoji": "🎵",
        "title": "🎵 SPOTIFY PREMIUM",
        "description": "🎶 Música sin anuncios y sin límites.\n♾️ Opción Lifetime disponible.",
        "items": [
            ("Premium KEY",  10.00, "🔑 Activás con tu cuenta"),
            ("Lifetime",     9.50,  "♾️ De por vida"),
        ],
    },
    "netflix": {
        "label": "🎬 Netflix 4K Lifetime",
        "category": "streaming",
        "emoji": "🎬",
        "title": "🎬 NETFLIX 4K — LIFETIME",
        "description": "📺 Contenido en 4K Ultra HD para siempre.\n♾️ Sin cuotas mensuales.",
        "items": [
            ("Netflix 4K Lifetime", 8.00, "♾️ De por vida"),
        ],
    },
    "prime_video": {
        "label": "📦 Prime Video Lifetime",
        "category": "streaming",
        "emoji": "📦",
        "title": "📦 PRIME VIDEO — LIFETIME",
        "description": "🎬 Cuenta privada con Gmail incluido.\n♾️ Sin cuotas mensuales.",
        "items": [
            ("Prime Video Lifetime", 15.00, "♾️ Privada + Gmail"),
        ],
    },
    "crunchyroll": {
        "label": "🍥 Crunchyroll MegaFan",
        "category": "streaming",
        "emoji": "🍥",
        "title": "🍥 CRUNCHYROLL — MEGAFAN LIFETIME",
        "description": "🎌 Anime sin anuncios y en HD para siempre.\n♾️ Plan MegaFan de por vida.",
        "items": [
            ("MegaFan Lifetime", 3.00, "♾️ De por vida"),
        ],
    },
    "hbo": {
        "label": "📺 HBO Max Lifetime",
        "category": "streaming",
        "emoji": "📺",
        "title": "📺 HBO MAX — LIFETIME",
        "description": "🍿 Series, películas y documentales sin fin.\n♾️ Sin cuotas mensuales.",
        "items": [
            ("HBO Max Lifetime", 4.50, "♾️ De por vida"),
        ],
    },
    "dazn_disney": {
        "label": "🏆 DAZN & Disney+",
        "category": "streaming",
        "emoji": "🏆",
        "title": "🏆 DAZN & DISNEY+",
        "description": "🎬 Plataformas de streaming premium al mejor precio.",
        "items": [
            ("DAZN Premium",             15.00, ""),
            ("Disney+ / Hulu / ESPN+",   10.00, "🌐 Requiere VPN"),
        ],
    },
    # ── IA & HERRAMIENTAS ────────────────────────────────────────
    "chatgpt": {
        "label": "🤖 ChatGPT Plus — 12 meses",
        "category": "tools",
        "emoji": "🤖",
        "title": "🤖 CHATGPT PLUS — 12 MESES",
        "description": "🧠 Acceso a GPT-4o, análisis de imágenes, DALL·E y más.\n📅 Suscripción por 12 meses.",
        "items": [
            ("ChatGPT Plus 12 meses", 20.00, ""),
        ],
    },
    "gemini": {
        "label": "✨ Gemini Advanced — 12 meses",
        "category": "tools",
        "emoji": "✨",
        "title": "✨ GEMINI ADVANCED (PRO+) — 12 MESES",
        "description": "🧠 IA de Google con acceso completo a Gemini Ultra.\n📅 Full Access por 12 meses.",
        "items": [
            ("Gemini Pro+ FA 12 meses", 20.00, ""),
        ],
    },
    "adobe": {
        "label": "🖌️ Adobe Creative Cloud",
        "category": "tools",
        "emoji": "🖌️",
        "title": "🖌️ ADOBE CREATIVE CLOUD — ALL APPS",
        "description": "🎨 Photoshop, Premiere, Illustrator y toda la suite Adobe.\n✔ All Apps incluido.",
        "items": [
            ("Adobe CC All Apps", 25.00, ""),
        ],
    },
    # ── DISEÑO & EDICIÓN ─────────────────────────────────────────
    "capcut": {
        "label": "✂️ CapCut Pro Lifetime",
        "category": "design",
        "emoji": "✂️",
        "title": "✂️ CAPCUT PRO — LIFETIME",
        "description": "🎬 Editor de video profesional sin marcas de agua.\n♾️ De por vida.",
        "items": [
            ("CapCut Pro Lifetime", 15.00, "♾️ De por vida"),
        ],
    },
    "canva": {
        "label": "🎨 Canva Pro Lifetime",
        "category": "design",
        "emoji": "🎨",
        "title": "🎨 CANVA PRO — LIFETIME",
        "description": "✏️ Diseñá sin límites: plantillas premium, fondos, elementos y más.\n♾️ De por vida.",
        "items": [
            ("Canva Pro Lifetime", 5.00, "♾️ De por vida"),
        ],
    },
}

CATEGORY_LABELS = {
    "fortnite":  "🎮 FORTNITE",
    "juegos":    "🕹️ JUEGOS",
    "streaming": "📺 STREAMING",
    "tools":     "🧠 IA & HERRAMIENTAS",
    "design":    "🎨 DISEÑO & EDICIÓN",
    "sellauth":  "🛒 TIENDA SELLAUTH",
}

def build_full_price_embed(product_key: str, moneda: str, rate: float) -> discord.Embed:
    info = FULL_PRICE_CATALOG.get(product_key)
    if not info:
        return discord.Embed(title="⛔ Producto no encontrado", color=EMBED_COLOR)

    embed = discord.Embed(
        title=info["title"],
        description=info["description"] + "\n\n━━━━━━━━━━━━━━━━━━",
        color=EMBED_COLOR
    )

    lines = []
    for label, usd, badge in info["items"]:
        precio = _fmt_money(usd, moneda, rate)
        suf = f"  {badge}" if badge else ""
        lines.append(f"**{label}** — {precio}{suf}")

    embed.add_field(name="💰 Precios", value="\n".join(lines), inline=False)
    embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━\n⬇️ *Cambiá moneda abajo*", inline=False)
    embed.set_footer(text="Base USD · Conversión automática · VortexGGShop")
    return embed

class PreciosCurrencySelect(discord.ui.Select):
    def __init__(self, product_key: str):
        self.product_key = product_key
        options = [
            discord.SelectOption(label=MONEDAS[c], value=c, emoji=EMOJIS[c])
            for c in MONEDAS
        ]
        super().__init__(
            placeholder="💱 Cambiá tu moneda",
            options=options,
            custom_id=f"precios_currency:{product_key}"
        )

    async def callback(self, interaction: discord.Interaction):
        moneda = self.values[0]
        rate = 1.0 if moneda == "USD" else await get_rate(moneda)
        embed = build_full_price_embed(self.product_key, moneda, rate)
        await interaction.response.edit_message(embed=embed, view=self.view)

class PreciosCurrencyView(discord.ui.View):
    def __init__(self, product_key: str):
        super().__init__(timeout=None)
        self.add_item(PreciosCurrencySelect(product_key))

class PreciosProductSelect(discord.ui.Select):
    def __init__(self):
        # Agrupar opciones por categoría
        options = []
        seen_categories = []
        for key, info in FULL_PRICE_CATALOG.items():
            cat = info["category"]
            if cat not in seen_categories:
                seen_categories.append(cat)
            options.append(
                discord.SelectOption(
                    label=info["label"],
                    value=key,
                    emoji=info["emoji"],
                    description=CATEGORY_LABELS.get(cat, "")
                )
            )
        super().__init__(
            placeholder="🛒 Elegí un producto para ver el precio",
            options=options,
            custom_id="precios_product_select"
        )

    async def callback(self, interaction: discord.Interaction):
        product_key = self.values[0]
        embed = build_full_price_embed(product_key, "USD", 1.0)
        view = PreciosCurrencyView(product_key)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PreciosProductView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PreciosProductSelect())

# =========================
# /postprecios (solo Staff/Admin)
# =========================
@bot.tree.command(name="postprecios", description="Publica el menú de precios en el canal (solo Staff)")
async def postprecios(
    interaction: discord.Interaction,
    canal: discord.TextChannel | None = None
):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Solo funciona en un servidor.", ephemeral=True)

    if not is_staff_or_admin(interaction):
        return await interaction.response.send_message("⛔ Solo Staff/Admin puede usar este comando.", ephemeral=True)

    target = canal or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await interaction.response.send_message("⛔ Elegí un canal de texto válido.", ephemeral=True)

    embed = discord.Embed(
        title="🛒 LISTA DE PRECIOS — VORTEXGGSHOP",
        description=(
            "Seleccioná un producto del menú desplegable para ver los precios detallados.\n"
            "También podés cambiar la moneda a la tuya 💱\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🎮 **FORTNITE:** Pavos, Crew, Cuentas\n"
            "🕹️ **OTROS JUEGOS:** Robux, Valorant, COD, GamePass\n"
            "💻 **SERVICIOS DIGITALES:** Spotify, Netflix, ChatGPT, Canva, HBO\n"
            "🎁 **MYSTERY BOXES:** Small, Medium, Mega\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⬇️ *Usá el menú de abajo para ver precios*"
        ),
        color=EMBED_COLOR
    )
    embed.set_footer(text="VortexGGShop · Precios en USD con conversión automática")

    await target.send(embed=embed, view=PreciosProductView())
    await interaction.response.send_message(f"✅ Menú de precios publicado en {target.mention}.", ephemeral=True)

# =========================
# /precios (mantener por compatibilidad)
# =========================
@bot.tree.command(name="precios", description="Muestra el menú de precios con selector de productos")
async def precios(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 LISTA DE PRECIOS — VORTEXGGSHOP",
        description=(
            "Seleccioná un producto del menú desplegable para ver los precios.\n\n"
            "⬇️ *Usá el menú de abajo*"
        ),
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed, view=PreciosProductView(), ephemeral=True)

# =========================
# /id
# =========================
@bot.tree.command(name="id", description="Cuenta para regalos")
async def id_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎁 Cuenta de regalos",
        description="Para agregar nuestra cuenta de regalos agregá a **VortexGifting1**.",
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed)

# =========================
# /staff
# =========================
@bot.tree.command(name="staff", description="Muestra quiénes son Staff y Owner")
async def staff(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True)

    guild = interaction.guild

    staff_role = next((r for r in guild.roles if r.name.lower() == "staff"), None)
    owner_role = next((r for r in guild.roles if r.name.lower() == "owner"), None)

    staff_members = staff_role.members if staff_role else []
    owner_members = owner_role.members if owner_role else []

    staff_list = "\n".join([m.mention for m in staff_members]) if staff_members else "—"
    owner_list = "\n".join([m.mention for m in owner_members]) if owner_members else "—"

    # Dueño del servidor (owner real)
    server_owner = guild.owner.mention if guild.owner else "—"

    embed = discord.Embed(
        title="🛡️ STAFF / OWNER",
        description="Estos son los roles a los que podés pedir ayuda dentro del servidor.",
        color=EMBED_COLOR
    )
    embed.add_field(name="👑 Owner del servidor", value=server_owner, inline=False)
    embed.add_field(name="👑 Rol @Owner", value=owner_list, inline=False)
    embed.add_field(name="🛡️ Rol @Staff", value=staff_list, inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# =========================
# /createembed — Constructor completo (solo Staff)
# =========================

EMBED_PRESETS = {
    "drop":      {"emoji": "✨", "color": 0x00FFAA, "ping": "@everyone"},
    "oferta":    {"emoji": "🔥", "color": 0xFF4500, "ping": "@everyone"},
    "info":      {"emoji": "📢", "color": 0x19B5FF, "ping": None},
    "aviso":     {"emoji": "⚠️", "color": 0xFFCC00, "ping": None},
    "giveaway":  {"emoji": "🎉", "color": 0xFF69B4, "ping": "@everyone"},
    "restock":   {"emoji": "🔄", "color": 0x9B59B6, "ping": "@everyone"},
    "custom":    {"emoji": "",   "color": 0x19B5FF, "ping": None},
}

EMBED_SEPARATORS = {
    "linea":    "━━━━━━━━━━━━━━━━━━━━━━━━",
    "puntos":   "• • • • • • • • • • • • •",
    "stars":    "✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦",
    "fire":     "🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥",
    "diamond":  "💎 ─── ✦ ─── 💎 ─── ✦ ─── 💎",
    "none":     "",
}

def _build_rich_embed(data: dict) -> discord.Embed:
    """Construye un embed rico a partir de un dict de configuración."""
    preset    = EMBED_PRESETS.get(data.get("tipo", "custom"), EMBED_PRESETS["custom"])
    color_hex = data.get("color_hex", "").strip().lstrip("#")
    if color_hex:
        try:
            color = discord.Color(int(color_hex, 16))
        except ValueError:
            color = discord.Color(preset["color"])
    else:
        color = discord.Color(preset["color"])

    titulo = data.get("titulo", "")
    emoji  = data.get("emoji_titulo", preset["emoji"])
    if emoji and not titulo.startswith(emoji):
        titulo = f"{emoji} {titulo}"

    sep_key = data.get("separador", "linea")
    sep     = EMBED_SEPARATORS.get(sep_key, EMBED_SEPARATORS["linea"])

    # Armar descripción con separadores y secciones extra
    partes = []
    if sep:
        partes.append(sep)

    desc = data.get("descripcion", "").strip()
    if desc:
        partes.append(desc)

    # Bullets opcionales (uno por línea, separados por |)
    bullets_raw = data.get("bullets", "").strip()
    if bullets_raw:
        if sep:
            partes.append(sep)
        for b in bullets_raw.split("|"):
            b = b.strip()
            if b:
                partes.append(f"🔑 {b}")

    # Link/CTA opcional
    cta_label = data.get("cta_label", "").strip()
    cta_url   = data.get("cta_url", "").strip()
    if cta_label and cta_url:
        if sep:
            partes.append(sep)
        partes.append(f"🛒 **{cta_label}**\n{cta_url}")

    if sep:
        partes.append(sep)

    descripcion_final = "\n".join(partes)

    embed = discord.Embed(
        title=titulo[:256],
        description=descripcion_final[:4096],
        color=color,
    )

    # Imagen principal (URL)
    img_url = data.get("imagen_url", "").strip()
    if img_url:
        embed.set_image(url=img_url)

    # Thumbnail (URL)
    thumb_url = data.get("thumbnail_url", "").strip()
    if thumb_url:
        embed.set_thumbnail(url=thumb_url)

    # Footer
    footer = data.get("footer", "VortexGGShop").strip()
    embed.set_footer(text=footer)

    return embed


class EmbedModal(discord.ui.Modal):
    """Modal principal para construir el embed."""

    titulo_field = discord.ui.TextInput(
        label="Título del embed",
        placeholder="Ej: NEW DROP: ChatGPT Plus [KEYS]!",
        max_length=200,
        required=True,
    )
    descripcion_field = discord.ui.TextInput(
        label="Descripción principal",
        style=discord.TextStyle.paragraph,
        placeholder="El texto principal del anuncio. Podés usar **negrita**, *cursiva*, etc.",
        max_length=2000,
        required=True,
    )
    bullets_field = discord.ui.TextInput(
        label="Bullets / Lista de precios (separar con |)",
        style=discord.TextStyle.paragraph,
        placeholder="1 Key: €2.35 | 10 Keys: €2.15 c/u | 25 Keys: €2.00 c/u",
        required=False,
        max_length=800,
    )
    cta_field = discord.ui.TextInput(
        label="Botón CTA: Texto | URL",
        placeholder="Comprá acá | https://vortexggshop.mysellauth.com/",
        required=False,
        max_length=300,
    )
    imagen_field = discord.ui.TextInput(
        label="URL de imagen (opcional)",
        placeholder="https://i.imgur.com/ejemplo.png",
        required=False,
        max_length=500,
    )

    def __init__(self, config: dict, canal: discord.TextChannel):
        super().__init__(title="✨ Crear Embed — Paso 2/2")
        self.config = config
        self.canal  = canal

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Parsear CTA
        cta_raw = str(self.cta_field.value).strip()
        cta_label, cta_url = "", ""
        if "|" in cta_raw:
            parts = cta_raw.split("|", 1)
            cta_label = parts[0].strip()
            cta_url   = parts[1].strip()

        data = {
            **self.config,
            "titulo":       str(self.titulo_field.value).strip(),
            "descripcion":  str(self.descripcion_field.value).strip(),
            "bullets":      str(self.bullets_field.value).strip(),
            "cta_label":    cta_label,
            "cta_url":      cta_url,
            "imagen_url":   str(self.imagen_field.value).strip(),
        }

        embed  = _build_rich_embed(data)
        preset = EMBED_PRESETS.get(data.get("tipo", "custom"), EMBED_PRESETS["custom"])
        ping   = data.get("ping_override") or preset["ping"]

        content = ping if ping else None
        await self.canal.send(content=content, embed=embed)
        await interaction.followup.send(
            f"✅ Embed publicado en {self.canal.mention}.", ephemeral=True
        )


class EmbedConfigView(discord.ui.View):
    """Paso 1: elegir tipo, separador y opciones antes del modal."""

    def __init__(self, canal: discord.TextChannel, staff: discord.Member):
        super().__init__(timeout=120)
        self.canal   = canal
        self.staff   = staff
        self.config  = {
            "tipo":       "custom",
            "separador":  "linea",
            "emoji_titulo": "",
            "color_hex":  "",
            "footer":     "VortexGGShop",
            "ping_override": None,
        }
        self._build_selects()

    def _build_selects(self):
        # Select tipo
        tipo_select = discord.ui.Select(
            placeholder="📌 Tipo de anuncio",
            custom_id="tipo_select",
            options=[
                discord.SelectOption(label="✨ New Drop",   value="drop",     description="Lanzamiento de producto"),
                discord.SelectOption(label="🔥 Oferta",     value="oferta",   description="Promoción / descuento"),
                discord.SelectOption(label="📢 Info",       value="info",     description="Anuncio general"),
                discord.SelectOption(label="⚠️ Aviso",      value="aviso",    description="Advertencia o aviso"),
                discord.SelectOption(label="🎉 Giveaway",   value="giveaway", description="Sorteo"),
                discord.SelectOption(label="🔄 Restock",    value="restock",  description="Restock de producto"),
                discord.SelectOption(label="🎨 Custom",     value="custom",   description="Sin preset"),
            ]
        )
        tipo_select.callback = self._tipo_callback
        self.add_item(tipo_select)

        # Select separador
        sep_select = discord.ui.Select(
            placeholder="✦ Separador decorativo",
            custom_id="sep_select",
            options=[
                discord.SelectOption(label="━ Línea",     value="linea",   description="━━━━━━━━━━━━━━━━"),
                discord.SelectOption(label="• Puntos",    value="puntos",  description="• • • • • • • •"),
                discord.SelectOption(label="✦ Stars",     value="stars",   description="✦ ✦ ✦ ✦ ✦ ✦ ✦"),
                discord.SelectOption(label="🔥 Fire",     value="fire",    description="🔥🔥🔥🔥🔥🔥🔥"),
                discord.SelectOption(label="💎 Diamond",  value="diamond", description="💎 ─── ✦ ─── 💎"),
                discord.SelectOption(label="❌ Sin sep.",  value="none",    description="Sin separador"),
            ]
        )
        sep_select.callback = self._sep_callback
        self.add_item(sep_select)

    async def _tipo_callback(self, interaction: discord.Interaction):
        self.config["tipo"] = interaction.data["values"][0]
        await interaction.response.defer()

    async def _sep_callback(self, interaction: discord.Interaction):
        self.config["separador"] = interaction.data["values"][0]
        await interaction.response.defer()

    @discord.ui.button(label="✨ Abrir editor", style=discord.ButtonStyle.success, row=2)
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.staff.id:
            return await interaction.response.send_message("⛔ No es tu comando.", ephemeral=True)
        await interaction.response.send_modal(EmbedModal(self.config, self.canal))

    @discord.ui.button(label="🎨 Color hex", style=discord.ButtonStyle.secondary, row=2)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.staff.id:
            return await interaction.response.send_message("⛔ No es tu comando.", ephemeral=True)

        class ColorModal(discord.ui.Modal, title="🎨 Color personalizado"):
            color_input = discord.ui.TextInput(
                label="Color en HEX",
                placeholder="Ej: FF4500  o  19B5FF",
                max_length=7,
                required=True,
            )
            footer_input = discord.ui.TextInput(
                label="Footer del embed",
                placeholder="VortexGGShop",
                max_length=100,
                required=False,
            )
            emoji_input = discord.ui.TextInput(
                label="Emoji delante del título (opcional)",
                placeholder="✨  🔥  🎉  💎",
                max_length=10,
                required=False,
            )

            async def on_submit(inner_self, inner_interaction: discord.Interaction):
                self.config["color_hex"]    = str(inner_self.color_input.value).strip().lstrip("#")
                self.config["footer"]       = str(inner_self.footer_input.value).strip() or "VortexGGShop"
                self.config["emoji_titulo"] = str(inner_self.emoji_input.value).strip()
                await inner_interaction.response.send_message(
                    f"✅ Color `#{self.config['color_hex']}` y opciones guardadas. Ahora hacé click en **✨ Abrir editor**.",
                    ephemeral=True
                )

        await interaction.response.send_modal(ColorModal())


@bot.tree.command(name="createembed", description="Crea un embed rico con imagen, bullets, CTA y efectos (solo Staff)")
@discord.app_commands.describe(canal="Canal donde se publicará el embed (por defecto: este canal)")
async def createembed(
    interaction: discord.Interaction,
    canal: discord.TextChannel | None = None,
):
    if not interaction.guild:
        return await interaction.response.send_message(
            "⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True
        )
    if not is_staff_only(interaction):
        return await interaction.response.send_message(
            "⛔ Solo el rol **Staff** puede usar este comando.", ephemeral=True
        )

    target = canal or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await interaction.response.send_message(
            "⛔ Elegí un canal de texto válido.", ephemeral=True
        )

    embed_guide = discord.Embed(
        title="✨ Constructor de Embeds — Paso 1/2",
        description=(
            "**1.** Elegí el **tipo de anuncio** y el **separador** decorativo.\n"
            "**2.** (Opcional) Hacé click en 🎨 **Color hex** para personalizar el color, footer y emoji.\n"
            "**3.** Hacé click en ✨ **Abrir editor** para escribir el contenido.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 **En el editor vas a poder poner:**\n"
            "• Título y descripción principal\n"
            "• Lista de precios/bullets separados por `|`\n"
            "• Botón CTA con texto y link\n"
            "• URL de imagen grande\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Tip:** Podés usar `**negrita**`, `*cursiva*` y saltos de línea en la descripción."
        ),
        color=EMBED_COLOR,
    )
    embed_guide.set_footer(text=f"Solicitado por {interaction.user} · VortexGGShop")

    view = EmbedConfigView(canal=target, staff=interaction.user)
    await interaction.response.send_message(embed=embed_guide, view=view, ephemeral=True)

# =========================
# /nuke (solo Staff)
# =========================
@bot.tree.command(name="nuke", description="Elimina TODOS los mensajes del canal actual (solo Staff)")
async def nuke(interaction: discord.Interaction, confirmacion: str = "NO"):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True)

    if not is_staff_only(interaction):
        return await interaction.response.send_message("⛔ Solo el rol **Staff** puede usar este comando.", ephemeral=True)

    if confirmacion.strip().upper() != "SI":
        return await interaction.response.send_message("⚠️ Para confirmar ejecutá: `/nuke SI`", ephemeral=True)

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message("⛔ Este comando solo funciona en canales de texto.", ephemeral=True)

    me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
    if me and not channel.permissions_for(me).manage_messages:
        return await interaction.response.send_message("⛔ No tengo permiso **Manage Messages** en este canal.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    deleted = 0
    try:
        while True:
            msgs = [m async for m in channel.history(limit=100)]
            if not msgs:
                break

            now = discord.utils.utcnow()
            recent = []
            old_msgs = []
            for m in msgs:
                if m.pinned:
                    continue
                age_days = (now - m.created_at).total_seconds() / 86400.0
                if age_days < 13.9:
                    recent.append(m)
                else:
                    old_msgs.append(m)

            if recent:
                await channel.delete_messages(recent)
                deleted += len(recent)

            for m in old_msgs:
                try:
                    await m.delete()
                    deleted += 1
                except Exception:
                    pass

            await asyncio.sleep(0.8)

        await interaction.followup.send(f"💥 Listo. Eliminé **{deleted}** mensajes en {channel.mention}.", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"⛔ Error durante nuke: `{e}`", ephemeral=True)

# =========================
# /borrarmensajes (solo Staff)
# =========================
@bot.tree.command(name="borrarmensajes", description="Borra mensajes de un usuario en un periodo (solo Staff)")
async def borrarmensajes(
    interaction: discord.Interaction,
    usuario: discord.Member,
    horas: discord.app_commands.Range[int, 1, 336],
    canal: discord.TextChannel | None = None
):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Este comando solo funciona dentro de un servidor.", ephemeral=True)

    if not is_staff_only(interaction):
        return await interaction.response.send_message("⛔ Solo el rol **Staff** puede usar este comando.", ephemeral=True)

    target = canal or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await interaction.response.send_message("⛔ Elegí un canal de texto válido.", ephemeral=True)

    me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
    if me and not target.permissions_for(me).manage_messages:
        return await interaction.response.send_message("⛔ No tengo permiso **Manage Messages** en ese canal.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    after_dt = discord.utils.utcnow() - timedelta(hours=int(horas))
    now = discord.utils.utcnow()

    bulk_batch = []
    deleted = 0
    scanned = 0
    MAX_SCAN = 5000

    async def flush_bulk():
        nonlocal bulk_batch, deleted
        if not bulk_batch:
            return
        try:
            await target.delete_messages(bulk_batch)
            deleted += len(bulk_batch)
        except Exception:
            # fallback: borrar 1 a 1
            for m in bulk_batch:
                try:
                    await m.delete()
                    deleted += 1
                except Exception:
                    pass
        bulk_batch = []

    try:
        async for msg in target.history(limit=MAX_SCAN, after=after_dt):
            scanned += 1
            if msg.pinned:
                continue
            if msg.author.id != usuario.id:
                continue

            age_days = (now - msg.created_at).total_seconds() / 86400.0
            if age_days < 13.9:
                bulk_batch.append(msg)
                if len(bulk_batch) >= 100:
                    await flush_bulk()
                    await asyncio.sleep(0.8)
            else:
                # viejo: borrar individual
                try:
                    await msg.delete()
                    deleted += 1
                except Exception:
                    pass

        await flush_bulk()

        await interaction.followup.send(
            f"✅ Eliminé **{deleted}** mensajes de {usuario.mention} en {target.mention} (últimas **{horas}** horas).",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(f"⛔ Error borrando mensajes: `{e}`", ephemeral=True)



# ================================================================
# SELLAUTH — PRODUCTOS EXTRA (desde /agregarproductos)
# ================================================================
EXTRA_PRODUCTS_FILE = Path("sellauth_products.json")
if not EXTRA_PRODUCTS_FILE.exists():
    EXTRA_PRODUCTS_FILE.write_text("{}")

def load_extra_products() -> dict:
    try:
        return json.loads(EXTRA_PRODUCTS_FILE.read_text())
    except Exception:
        return {}

def save_extra_products(data: dict):
    EXTRA_PRODUCTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def merge_extra_products():
    """Inyecta los productos de SellAuth en FULL_PRICE_CATALOG al arrancar."""
    extra = load_extra_products()
    for k, v in extra.items():
        if k not in FULL_PRICE_CATALOG:
            FULL_PRICE_CATALOG[k] = v
    if extra and "sellauth" not in CATEGORY_LABELS:
        CATEGORY_LABELS["sellauth"] = "🛒 TIENDA SELLAUTH"

# ================================================================
# SELLAUTH — ESTADO DE INVOICES (para el log de ventas)
# ================================================================
LAST_INVOICES_FILE = Path("last_invoices.json")
if not LAST_INVOICES_FILE.exists():
    LAST_INVOICES_FILE.write_text(
        json.dumps({"seen_ids": [], "channel_id": None}, indent=2)
    )

def load_invoice_state() -> dict:
    try:
        return json.loads(LAST_INVOICES_FILE.read_text())
    except Exception:
        return {"seen_ids": [], "channel_id": None}

def save_invoice_state(data: dict):
    LAST_INVOICES_FILE.write_text(json.dumps(data, indent=2))

# ================================================================
# SELLAUTH — HTTP HELPER
# ================================================================
async def sellauth_request(method: str, endpoint: str, **kwargs):
    """Hace una petición autenticada a la API de SellAuth."""
    headers = {
        "Authorization": f"Bearer {SELLAUTH_API_KEY}",
        "Accept": "application/json",
        "Accept-Encoding": "identity",  # Sin compresión — evita brotli que aiohttp no soporta
    }
    url = f"{SELLAUTH_BASE_URL}/{endpoint}"
    try:
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.request(
                method, url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
                **kwargs
            ) as resp:
                raw = await resp.read()
                text = raw.decode("utf-8", errors="replace")
                if resp.status == 200:
                    return json.loads(text)
                print(f"[SellAuth] {method} {endpoint} → HTTP {resp.status}: {text[:300]}")
                return None
    except Exception as e:
        print(f"[SellAuth] Error en request {endpoint}: {e}")
        return None

# ================================================================
# SELLAUTH — LOG DE VENTAS (tarea en loop)
# ================================================================
async def get_or_create_sales_log(guild: discord.Guild) -> discord.TextChannel | None:
    """Obtiene o crea el canal de logs de ventas."""
    existing = discord.utils.get(guild.text_channels, name=SALES_LOG_CHANNEL_NAME)
    if existing:
        return existing
    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True),
        }
        staff_role = next((r for r in guild.roles if r.name.lower() == "staff"), None)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        channel = await guild.create_text_channel(
            name=SALES_LOG_CHANNEL_NAME,
            topic="📦 Log automático de ventas · VortexGGShop × SellAuth",
            overwrites=overwrites,
        )
        return channel
    except Exception as e:
        print(f"[SalesLog] No pude crear el canal: {e}")
        return None

def _mask_email(email: str) -> str:
    parts = email.split("@")
    if len(parts) == 2:
        return parts[0][:2] + "***@" + parts[1]
    return "***"

@tasks.loop(minutes=2)
async def sales_log_task():
    """Revisa nuevas ventas en SellAuth cada 2 minutos y las postea en el log."""
    state = load_invoice_state()
    seen_ids: set = set(state.get("seen_ids", []))

    data = await sellauth_request("GET", f"shops/{SELLAUTH_SHOP_ID}/invoices")
    if data is None:
        return

    invoices = data if isinstance(data, list) else data.get("data", [])

    new_sales = []
    for inv in invoices:
        inv_id = str(inv.get("id", ""))
        if not inv_id or inv_id in seen_ids:
            continue
        # Solo marcar como visto si ya está completado/pagado.
        # Las facturas pendientes se re-revisan en el próximo ciclo.
        if str(inv.get("status", "")).lower() in ("completed", "paid"):
            seen_ids.add(inv_id)
            new_sales.append(inv)

    # Guardar estado actualizado
    state["seen_ids"] = list(seen_ids)[-500:]
    save_invoice_state(state)

    if not new_sales:
        return

    # Encontrar/crear canal de log
    channel_id = state.get("channel_id")
    log_channel: discord.TextChannel | None = None
    if channel_id:
        log_channel = bot.get_channel(int(channel_id))

    if log_channel is None:
        for guild in bot.guilds:
            log_channel = await get_or_create_sales_log(guild)
            if log_channel:
                state["channel_id"] = log_channel.id
                save_invoice_state(state)
                break

    if log_channel is None:
        return

    for inv in new_sales:
        # Productos desde items[] (API real de SellAuth)
        items = inv.get("items") or []
        if items:
            product_names = []
            for it in items:
                p_name = (it.get("product") or {}).get("name", "")
                v_name = (it.get("variant")  or {}).get("name", "")
                if p_name and v_name:
                    product_names.append(f"{p_name} — {v_name}")
                elif p_name:
                    product_names.append(p_name)
            product_name = "\n".join(product_names) or "Producto"
        else:
            product_name = inv.get("product_name") or "Producto"

        price    = inv.get("price_usd") or inv.get("price") or "?"
        currency = inv.get("currency", "USD")
        inv_id   = str(inv.get("unique_id") or inv.get("id", "?"))
        email    = inv.get("email", "")
        quantity = inv.get("amount", 1)
        gateway  = inv.get("gateway") or (inv.get("payment_method") or {}).get("name", "—")

        embed = discord.Embed(
            title="🛒 NUEVA VENTA — VORTEXGGSHOP",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="📦 Producto",    value=product_name[:1024],                   inline=False)
        embed.add_field(name="💰 Monto",        value=f"**${price} {currency}**",             inline=True)
        embed.add_field(name="🔢 Cantidad",     value=str(quantity),                          inline=True)
        embed.add_field(name="💳 Método",       value=str(gateway),                           inline=True)
        embed.add_field(name="📧 Cliente",      value=_mask_email(email) if email else "—",   inline=True)
        embed.add_field(name="🧾 Invoice ID",   value=f"`{inv_id}`",                          inline=True)
        embed.set_footer(text="VortexGGShop · SellAuth")
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"[SalesLog] Error enviando embed: {e}")

@sales_log_task.before_loop
async def before_sales_log():
    await bot.wait_until_ready()

# ================================================================
# /invoice — Verificar una compra por ID
# ================================================================
@bot.tree.command(name="invoice", description="Verificá el estado de una compra por Invoice ID")
async def invoice_cmd(
    interaction: discord.Interaction,
    invoice_id: str,
):
    await interaction.response.defer()  # público — lo ve todo el canal

    data = await sellauth_request("GET", f"shops/{SELLAUTH_SHOP_ID}/invoices/{invoice_id}")

    if data is None:
        embed = discord.Embed(
            title="❌ Invoice no encontrado",
            description=(
                f"```{invoice_id}```\n"
                "No se encontró ninguna compra con ese ID.\n\n"
                "**Posibles causas:**\n"
                "▸ El ID no es correcto\n"
                "▸ La compra fue realizada hace mucho tiempo\n"
                "▸ Si acabás de comprar, esperá unos segundos\n\n"
                f"🌐 También podés revisar en [vortexggshop.mysellauth.com]({WEBSITE_URL})"
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="VortexGGShop · Sistema de verificación")
        return await interaction.followup.send(embed=embed)

    status = str(data.get("status", "unknown")).lower()
    status_map = {
        "completed":  ("✅ Completada",   discord.Color.green()),
        "paid":       ("✅ Pagada",        discord.Color.green()),
        "pending":    ("⏳ Pendiente",     discord.Color.yellow()),
        "refunded":   ("🔄 Reembolsada",  discord.Color.orange()),
        "cancelled":  ("❌ Cancelada",    discord.Color.red()),
        "chargeback": ("⚠️ Chargeback",   discord.Color.red()),
    }
    status_label, color = status_map.get(status, (f"❓ {status.capitalize()}", EMBED_COLOR))

    # Productos desde items[] (estructura real de SellAuth)
    inv_items = data.get("items") or []
    if inv_items:
        product_lines = []
        for it in inv_items:
            p_name = (it.get("product") or {}).get("name", "")
            v_name = (it.get("variant")  or {}).get("name", "")
            if p_name and v_name:
                product_lines.append(f"▸ {p_name} — {v_name}")
            elif p_name:
                product_lines.append(f"▸ {p_name}")
        prod_name = "\n".join(product_lines) or "N/A"
    else:
        prod_name = data.get("product_name") or "N/A"

    price      = data.get("price_usd") or data.get("price") or "N/A"
    currency   = data.get("currency", "USD")
    quantity   = data.get("amount", 1)
    created_at = str(data.get("created_at", "N/A"))[:19].replace("T", " ")
    completed  = str(data.get("completed_at") or "—")[:19].replace("T", " ")
    email      = data.get("email", "")
    gateway    = data.get("gateway") or (data.get("payment_method") or {}).get("name", "N/A")
    unique_id  = data.get("unique_id") or str(data.get("id", invoice_id))

    embed = discord.Embed(
        title="🧾 VERIFICACIÓN DE COMPRA",
        description=(
            f"**Estado:** {status_label}\n"
            f"━━━━━━━━━━━━━━━━━━"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="📌 Invoice ID",
        value=f"```{unique_id}```",
        inline=False,
    )
    embed.add_field(
        name="📦 Producto(s)",
        value=prod_name[:1024],
        inline=False,
    )
    embed.add_field(name="💰 Monto",       value=f"**${price} {currency}**", inline=True)
    embed.add_field(name="🔢 Cantidad",    value=str(quantity),               inline=True)
    embed.add_field(name="💳 Método",      value=str(gateway),                inline=True)
    embed.add_field(name="📅 Fecha",       value=created_at,                  inline=True)
    embed.add_field(name="✅ Completado",  value=completed,                   inline=True)
    if email:
        embed.add_field(name="📧 Cliente", value=f"||{_mask_email(email)}||", inline=True)

    embed.set_footer(
        text=f"VortexGGShop · Verificado por {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url,
    )

    await interaction.followup.send(embed=embed)

# ================================================================
# SELLAUTH — helper para crear producto
# ================================================================
async def sellauth_create_product(name: str, description: str, variants: list[dict]) -> dict | None:
    """Crea un producto en SellAuth. variants = [{"name": str, "price": float}, ...]"""
    # Precio base = variante más barata (SellAuth lo requiere)
    base_price = min(v["price"] for v in variants) if variants else 0.0

    payload = {
        "name":        name,
        "description": description,
        "price":       str(round(base_price, 2)),
        "currency":    "USD",
        "type":        "service",   # tipo genérico para servicios digitales
        "unlisted":    False,
    }

    result = await sellauth_request(
        "POST",
        f"shops/{SELLAUTH_SHOP_ID}/products",
        json=payload,
    )

    # Si tiene múltiples variantes, intentamos crearlas
    if result and len(variants) > 1:
        pid = result.get("id") or (result.get("data") or {}).get("id")
        if pid:
            for v in variants:
                await sellauth_request(
                    "POST",
                    f"shops/{SELLAUTH_SHOP_ID}/products/{pid}/variants",
                    json={"name": v["name"], "price": str(round(v["price"], 2))},
                )

    return result

# ================================================================
# /agregarproductos — Sync bidireccional catálogo ↔ SellAuth
# ================================================================
@bot.tree.command(name="agregarproductos", description="Sincroniza el catálogo con SellAuth: sube los del bot que falten y baja los de SellAuth (solo Staff)")
async def agregarproductos(interaction: discord.Interaction):
    if not is_staff_or_admin(interaction):
        return await interaction.response.send_message(
            "⛔ Solo Staff/Admin puede usar este comando.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    # ── 1. Traer lista actual de SellAuth ─────────────────────────
    sa_data = await sellauth_request("GET", f"shops/{SELLAUTH_SHOP_ID}/products")
    if sa_data is None:
        return await interaction.followup.send(
            "⛔ No se pudo conectar con SellAuth.\n"
            "Verificá `SELLAUTH_API_KEY` y `SELLAUTH_SHOP_ID` en las variables de entorno de Railway.",
            ephemeral=True,
        )

    sa_products = sa_data if isinstance(sa_data, list) else sa_data.get("data", [])
    # Nombres ya en SellAuth (para no duplicar)
    sa_names_existing = {str(p.get("name", "")).lower() for p in sa_products}

    # ── 2. Subir productos del catálogo local que no estén en SellAuth ──
    uploaded   = []
    upload_err = []

    for key, info in FULL_PRICE_CATALOG.items():
        if info.get("category") == "sellauth":
            continue   # ya vienen de SellAuth, no resubir
        prod_title = info["title"].lstrip("🪙🎟️🔫🎮⚔️🎵🎬📦🍥📺🏆🤖✨🖌️✂️🎨 ").strip()
        if prod_title.lower() in sa_names_existing:
            continue   # ya existe en SellAuth

        variants = [
            {"name": item[0], "price": float(item[1])}
            for item in info.get("items", [])
        ]
        desc_clean = re.sub(r"[^\x20-\x7E\n·•áéíóúÁÉÍÓÚñÑ♾️🔥⭐💎✔📅🧠🎶📺🍿🎌🌐]", "", info.get("description", ""))[:500]

        result = await sellauth_create_product(prod_title, desc_clean, variants)
        if result:
            uploaded.append(prod_title)
        else:
            upload_err.append(prod_title)

    # ── 3. Bajar productos de SellAuth que no estén en el bot ─────
    extra   = load_extra_products()
    pulled  = []
    skipped = []

    for p in sa_products:
        pid = str(p.get("id", ""))
        key = f"sa_{pid}"
        if key in extra or key in FULL_PRICE_CATALOG:
            skipped.append(p.get("name", pid))
            continue

        title       = str(p.get("name") or "Producto")
        raw_desc    = str(p.get("description", "") or "")
        description = re.sub(r"<[^>]+>", "", raw_desc).strip()[:200] or "Sin descripción"

        items: list[tuple] = []
        for v in (p.get("variants") or []):
            v_name  = str(v.get("name") or "")
            v_price = float(v.get("price") or 0)
            if v_name:
                items.append((v_name, v_price, ""))
        if not items:
            items = [(title, float(p.get("price") or 0), "")]

        extra[key] = {
            "label":       f"🛒 {title[:40]}",
            "category":    "sellauth",
            "emoji":       "🛒",
            "title":       f"🛒 {title}",
            "description": description,
            "items":       items,
        }
        pulled.append(title)

    if pulled:
        save_extra_products(extra)
        merge_extra_products()
        for k in extra:
            bot.add_view(PreciosCurrencyView(k))

    # ── 4. Respuesta ──────────────────────────────────────────────
    embed = discord.Embed(
        title="🔄 SYNC CATÁLOGO ↔ SELLAUTH",
        color=EMBED_COLOR,
    )

    def _fmt_list(items_list: list) -> str:
        txt = "\n".join(f"• {n}" for n in items_list)
        return txt[:1000] + ("…" if len(txt) > 1000 else "") if txt else "—"

    embed.add_field(
        name=f"⬆️ Subidos a SellAuth ({len(uploaded)})",
        value=_fmt_list(uploaded),
        inline=False,
    )
    if upload_err:
        embed.add_field(
            name=f"⚠️ Error al subir ({len(upload_err)})",
            value=_fmt_list(upload_err),
            inline=False,
        )
    embed.add_field(
        name=f"⬇️ Bajados desde SellAuth ({len(pulled)})",
        value=_fmt_list(pulled),
        inline=False,
    )
    if skipped:
        embed.add_field(
            name=f"⏭️ Ya existían en SellAuth ({len(skipped)})",
            value=", ".join(skipped[:20]) + ("…" if len(skipped) > 20 else ""),
            inline=False,
        )

    embed.set_footer(text=f"Productos en catálogo del bot: {len(FULL_PRICE_CATALOG)}")
    await interaction.followup.send(embed=embed, ephemeral=True)

# ================================================================
# /setupventas — Crear canal de logs manualmente (solo Admin)
# ================================================================
@bot.tree.command(name="setupventas", description="Crea el canal de logs de ventas automático (solo Admin)")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setupventas(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Solo funciona en un servidor.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    channel = await get_or_create_sales_log(interaction.guild)
    if channel is None:
        return await interaction.followup.send(
            "⛔ No pude crear el canal. Verificá que el bot tenga permisos de **Manage Channels**.",
            ephemeral=True,
        )

    state = load_invoice_state()
    state["channel_id"] = channel.id
    save_invoice_state(state)

    embed = discord.Embed(
        title="✅ Canal de ventas configurado",
        description=(
            f"📦 El canal {channel.mention} fue creado y vinculado.\n\n"
            "Cada vez que alguien compre en tu tienda SellAuth, "
            "la venta aparecerá automáticamente ahí.\n\n"
            "⏱️ El bot revisa nuevas ventas **cada 2 minutos**."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="VortexGGShop · SellAuth Integration")
    await interaction.followup.send(embed=embed, ephemeral=True)

# =========================
# OWNER ID (copia fija de sendp y replace)
# =========================
OWNER_ID = 1410689876852084897

async def _enviar_copia_owner(bot, copia_embed: discord.Embed):
    """Manda la copia al owner fijo por DM."""
    try:
        owner = await bot.fetch_user(OWNER_ID)
        await owner.send(embed=copia_embed)
    except Exception:
        pass

# =========================
# /sendp — Envía producto por DM al cliente (solo Staff)
# =========================
@bot.tree.command(
    name="sendp",
    description="Envía el producto comprado por DM al cliente (solo Staff)"
)
@discord.app_commands.describe(
    cliente="Usuario de Discord al que le enviás el producto",
    producto="Nombre del producto que compró",
    detalle="Información del producto (clave, link, instrucciones, etc.)",
    imagen="Captura o imagen del producto (opcional)",
    nota="Nota extra para el cliente (opcional)"
)
async def sendp(
    interaction: discord.Interaction,
    cliente: discord.Member,
    producto: str,
    detalle: str,
    imagen: discord.Attachment | None = None,
    nota: str | None = None
):
    await interaction.response.defer(ephemeral=True)

    if not is_staff_or_owner(interaction):
        return await interaction.followup.send(
            "⛔ Solo Staff/Owner puede usar este comando.", ephemeral=True
        )

    if imagen is not None:
        allowed = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")
        if imagen.content_type not in allowed:
            return await interaction.followup.send(
                "⛔ Solo se permiten imágenes (PNG, JPG, GIF, WEBP).", ephemeral=True
            )

    # ── Embed para el cliente ────────────────────────────────────
    embed = discord.Embed(
        title="📦 TU PRODUCTO ESTÁ LISTO — VORTEXGGSHOP",
        description=(
            f"¡Hola {cliente.mention}! Tu compra fue procesada exitosamente.\n"
            f"Acá abajo encontrás los detalles de tu producto."
        ),
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🛒 Producto",          value=f"**{producto}**",           inline=False)
    embed.add_field(name="📋 Detalle / Entrega", value=f"```\n{detalle}\n```",      inline=False)
    if nota:
        embed.add_field(name="📝 Nota",          value=nota,                        inline=False)
    embed.add_field(
        name="❓ ¿Algún problema?",
        value="Abrí un ticket en nuestro servidor o contactá a un Staff.",
        inline=False
    )
    if interaction.guild and interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    embed.set_footer(text=f"Gestionado por {interaction.user} · VortexGGShop")
    if imagen is not None:
        embed.set_image(url=imagen.url)

    # ── Embed de log interno ─────────────────────────────────────
    copia_embed = discord.Embed(
        title="📋 ENTREGA REGISTRADA",
        description=f"**{interaction.user}** entregó un producto a **{cliente}**.",
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    copia_embed.add_field(name="🛒 Producto",  value=producto,                              inline=True)
    copia_embed.add_field(name="👤 Cliente",   value=f"{cliente}\n`{cliente.id}`",          inline=True)
    copia_embed.add_field(name="🛡️ Staff",    value=f"{interaction.user}",                 inline=True)
    copia_embed.add_field(name="📋 Detalle",   value=f"```\n{detalle}\n```",               inline=False)
    if nota:
        copia_embed.add_field(name="📝 Nota",  value=nota,                                 inline=False)
    copia_embed.set_footer(text="VortexGGShop · Log interno")
    if imagen is not None:
        copia_embed.set_image(url=imagen.url)

    # ── Envío al cliente ─────────────────────────────────────────
    try:
        await cliente.send(embed=embed)
    except discord.Forbidden:
        return await interaction.followup.send(
            f"⛔ No pude enviarle el DM a {cliente.mention}. Tiene los mensajes directos desactivados.",
            ephemeral=True
        )
    except Exception as e:
        return await interaction.followup.send(f"⛔ Error inesperado al enviar DM: `{e}`", ephemeral=True)

    # ── Log en el ticket actual ──────────────────────────────────
    try:
        await interaction.channel.send(embed=copia_embed)
    except Exception:
        pass

    # ── Copia al owner por DM ────────────────────────────────────
    await _enviar_copia_owner(bot, copia_embed)

    # Copia al staff que lo ejecutó (si no es el owner)
    if interaction.user.id != OWNER_ID:
        try:
            await interaction.user.send(embed=copia_embed)
        except discord.Forbidden:
            pass

    await interaction.followup.send(
        f"✅ Producto enviado por DM a {cliente.mention}.",
        ephemeral=True
    )


# =========================
# /replace — Envía reemplazo por DM al cliente (solo Staff)
# =========================
@bot.tree.command(
    name="replace",
    description="Envía un reemplazo de producto por DM al cliente (solo Staff)"
)
@discord.app_commands.describe(
    cliente="Usuario de Discord al que le enviás el reemplazo",
    producto_original="Nombre del producto original que falló",
    producto_nuevo="Nombre del producto de reemplazo",
    detalle="Información del reemplazo (clave, link, instrucciones, etc.)",
    imagen="Captura o imagen del reemplazo (opcional)",
    motivo="Motivo del reemplazo (opcional)"
)
async def replace(
    interaction: discord.Interaction,
    cliente: discord.Member,
    producto_original: str,
    producto_nuevo: str,
    detalle: str,
    imagen: discord.Attachment | None = None,
    motivo: str | None = None
):
    await interaction.response.defer(ephemeral=True)

    if not is_staff_or_owner(interaction):
        return await interaction.followup.send(
            "⛔ Solo Staff/Owner puede usar este comando.", ephemeral=True
        )

    if imagen is not None:
        allowed = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")
        if imagen.content_type not in allowed:
            return await interaction.followup.send(
                "⛔ Solo se permiten imágenes (PNG, JPG, GIF, WEBP).", ephemeral=True
            )

    # ── Embed para el cliente ────────────────────────────────────
    embed = discord.Embed(
        title="🔄 REEMPLAZO EFECTUADO — VORTEXGGSHOP",
        description=(
            f"Hola {cliente.mention}, realizamos un reemplazo de tu producto.\n"
            f"Abajo encontrás los detalles del nuevo ítem."
        ),
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="❌ Producto original",  value=f"~~{producto_original}~~", inline=True)
    embed.add_field(name="✅ Producto nuevo",      value=f"**{producto_nuevo}**",   inline=True)
    embed.add_field(name="\u200b",                value="\u200b",                   inline=False)
    embed.add_field(name="📋 Detalle / Entrega",  value=f"```\n{detalle}\n```",    inline=False)
    if motivo:
        embed.add_field(name="📌 Motivo",         value=motivo,                     inline=False)
    embed.add_field(
        name="❓ ¿Algún problema con el reemplazo?",
        value="Abrí un ticket en nuestro servidor o contactá a un Staff.",
        inline=False
    )
    if interaction.guild and interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    embed.set_footer(text=f"Gestionado por {interaction.user} · VortexGGShop")
    if imagen is not None:
        embed.set_image(url=imagen.url)

    # ── Embed de log interno ─────────────────────────────────────
    copia_embed = discord.Embed(
        title="🔄 REEMPLAZO REGISTRADO",
        description=f"**{interaction.user}** envió un reemplazo a **{cliente}**.",
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    copia_embed.add_field(name="❌ Original",     value=producto_original,                  inline=True)
    copia_embed.add_field(name="✅ Reemplazo",    value=producto_nuevo,                     inline=True)
    copia_embed.add_field(name="👤 Cliente",      value=f"{cliente}\n`{cliente.id}`",       inline=True)
    copia_embed.add_field(name="🛡️ Staff",       value=f"{interaction.user}",              inline=True)
    copia_embed.add_field(name="📋 Detalle",      value=f"```\n{detalle}\n```",            inline=False)
    if motivo:
        copia_embed.add_field(name="📌 Motivo",   value=motivo,                             inline=False)
    copia_embed.set_footer(text="VortexGGShop · Log interno")
    if imagen is not None:
        copia_embed.set_image(url=imagen.url)

    # ── Envío al cliente ─────────────────────────────────────────
    try:
        await cliente.send(embed=embed)
    except discord.Forbidden:
        return await interaction.followup.send(
            f"⛔ No pude enviarle el DM a {cliente.mention}. Tiene los mensajes directos desactivados.",
            ephemeral=True
        )
    except Exception as e:
        return await interaction.followup.send(f"⛔ Error inesperado al enviar DM: `{e}`", ephemeral=True)

    # ── Log en el ticket actual ──────────────────────────────────
    try:
        await interaction.channel.send(embed=copia_embed)
    except Exception:
        pass

    # ── Copia al owner por DM ────────────────────────────────────
    await _enviar_copia_owner(bot, copia_embed)

    # Copia al staff que lo ejecutó (si no es el owner)
    if interaction.user.id != OWNER_ID:
        try:
            await interaction.user.send(embed=copia_embed)
        except discord.Forbidden:
            pass

    await interaction.followup.send(
        f"✅ Reemplazo enviado por DM a {cliente.mention}.",
        ephemeral=True
    )


# ================================================================
# RESTOCK POLLING — Detecta subidas de stock y avisa en Discord
# ================================================================
STOCK_SNAPSHOT_FILE = Path("stock_snapshot.json")
if not STOCK_SNAPSHOT_FILE.exists():
    STOCK_SNAPSHOT_FILE.write_text("{}")

def load_stock_snapshot() -> dict:
    try:
        return json.loads(STOCK_SNAPSHOT_FILE.read_text())
    except Exception:
        return {}

def save_stock_snapshot(data: dict):
    STOCK_SNAPSHOT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

async def _get_or_create_restock_channel() -> discord.TextChannel | None:
    """Busca o crea el canal de restock automáticamente."""
    for guild in bot.guilds:
        ch = discord.utils.get(guild.text_channels, name=RESTOCK_CHANNEL_NAME)
        if ch:
            return ch
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                ),
            }
            if guild.me:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                )
            ch = await guild.create_text_channel(
                name=RESTOCK_CHANNEL_NAME,
                topic="📦 Notificaciones de restock automáticas · VortexGGShop",
                overwrites=overwrites,
            )
            print(f"[Restock] Canal '{RESTOCK_CHANNEL_NAME}' creado en {guild.name}")
            return ch
        except Exception as e:
            print(f"[Restock] No pude crear el canal: {e}")
    return None

@tasks.loop(minutes=RESTOCK_POLL_MINUTES)
async def restock_poll_task():
    """Revisa el stock de todos los productos en SellAuth y notifica si subió."""
    data = await sellauth_request("GET", f"shops/{SELLAUTH_SHOP_ID}/products")
    if data is None:
        return

    products = data if isinstance(data, list) else data.get("data", [])
    if not products:
        return

    snapshot = load_stock_snapshot()
    restocked = []

    for p in products:
        pid       = str(p.get("id", ""))
        name      = str(p.get("name") or "Producto")
        buy_url   = p.get("url") or WEBSITE_URL

        # Stock actual — puede estar en el producto o en sus variantes
        variants = p.get("variants") or []
        if variants:
            stock = sum(int(v.get("stock") or 0) for v in variants)
        else:
            stock = int(p.get("stock") or 0)

        prev_stock = int(snapshot.get(pid, {}).get("stock", -1))

        # Si el stock subió respecto al snapshot anterior → restock
        # Si es producto nuevo con stock > 0 → también avisamos
        if stock > 0 and (prev_stock == -1 or stock > prev_stock):
            # ── Traer detalles completos del producto (precio e imagen) ──
            detail = await sellauth_request("GET", f"shops/{SELLAUTH_SHOP_ID}/products/{pid}")
            if detail:
                # Precio: intentar desde variantes o campo directo
                detail_variants = detail.get("variants") or []
                if detail_variants:
                    prices = [float(v.get("price") or 0) for v in detail_variants if v.get("price")]
                    price    = min(prices) if prices else None
                    currency = (detail_variants[0].get("currency") or detail.get("currency") or "EUR")
                else:
                    price    = detail.get("price") or detail.get("minimum_price")
                    currency = detail.get("currency") or "EUR"
                # Imagen
                image_url = (
                    detail.get("image_url") or
                    detail.get("image") or
                    (detail.get("images") or [None])[0] or
                    None
                )
                # Si image_url es un dict (objeto), sacar la url
                if isinstance(image_url, dict):
                    image_url = image_url.get("url") or image_url.get("path") or None
            else:
                price     = p.get("price") or p.get("minimum_price") or None
                currency  = p.get("currency") or "EUR"
                image_url = p.get("image") or p.get("image_url") or None

            restocked.append({
                "name":      name,
                "price":     price,
                "currency":  currency,
                "stock":     stock,
                "image_url": image_url,
                "buy_url":   buy_url,
                "is_new":    prev_stock == -1,
            })

        # Actualizar snapshot
        snapshot[pid] = {"stock": stock, "name": name}

    save_stock_snapshot(snapshot)

    if not restocked:
        return

    channel = await _get_or_create_restock_channel()
    if not channel:
        return

    for item in restocked:
        # Formatear precio
        try:
            price_fmt = f"{float(item['price']):.2f} {item['currency']}" if item['price'] is not None else f"Ver tienda"
        except Exception:
            price_fmt = f"{item['price']} {item['currency']}" if item['price'] else "Ver tienda"

        titulo = f"🆕 {item['name']} - NEW PRODUCT" if item.get("is_new") else f"🔁 {item['name']} - RESTOCKED"

        embed = discord.Embed(
            title=titulo,
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🧱 Service",         value=item["name"],          inline=False)
        embed.add_field(name="📦 Available stock", value=str(item["stock"]),    inline=True)
        embed.add_field(name="💰 Price",           value=price_fmt,             inline=True)
        embed.add_field(
            name="ℹ️ Information",
            value="We just added this product to our store!" if item.get("is_new") else "We have recently restocked this product!",
            inline=False
        )
        if item["image_url"]:
            embed.set_image(url=item["image_url"])

        embed.set_footer(text="VortexGGShop · Stock Notifications")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="BUY NOW 🔗", url=item["buy_url"], style=discord.ButtonStyle.link))

        try:
            await channel.send(content="@everyone", embed=embed, view=view)
        except Exception as e:
            print(f"[Restock] Error enviando embed: {e}")

@restock_poll_task.before_loop
async def before_restock_poll():
    await bot.wait_until_ready()

# =========================
# /setuprestock — Crear canal de restock manualmente (solo Admin)
# =========================
@bot.tree.command(name="setuprestock", description="Crea el canal de notificaciones de restock (solo Admin)")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setuprestock(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("⛔ Solo funciona en un servidor.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    channel = await _get_or_create_restock_channel()
    if channel is None:
        return await interaction.followup.send(
            "⛔ No pude crear el canal. Verificá que el bot tenga permisos de **Manage Channels**.",
            ephemeral=True,
        )

    embed = discord.Embed(
        title="✅ Canal de restock configurado",
        description=(
            f"📦 El canal {channel.mention} fue creado.\n\n"
            f"El bot revisará el stock cada **{RESTOCK_POLL_MINUTES} minutos** "
            "y avisará automáticamente cuando haya restock."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="VortexGGShop · Restock Notifications")
    await interaction.followup.send(embed=embed, ephemeral=True)


# =========================
# RUN
# =========================
merge_extra_products()   # Cargar productos guardados al arrancar

print("DEBUG CONFIG:")
print("DISCORD_BOT_TOKEN/TOKEN cargado:", bool(TOKEN))
print("DISCORD_BOT_TOKEN/TOKEN length:", len(TOKEN) if TOKEN else 0)
print("SELLAUTH_API_KEY cargada:", bool(SELLAUTH_API_KEY))
print("SELLAUTH_SHOP_ID cargado:", bool(SELLAUTH_SHOP_ID))
print("SELLAUTH_BASE_URL:", SELLAUTH_BASE_URL)
print("WEBSITE_URL:", WEBSITE_URL)
print("VOUCHES_CHANNEL_ID:", VOUCHES_CHANNEL_ID)
print("SALES_LOG_CHANNEL_NAME:", SALES_LOG_CHANNEL_NAME)
print("RESTOCK_CHANNEL_NAME:", RESTOCK_CHANNEL_NAME)
print("RESTOCK_POLL_MINUTES:", RESTOCK_POLL_MINUTES)

bot.run(TOKEN)
