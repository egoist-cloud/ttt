"""
Quantum - бот клана (v18: исправлен Cloudflare 429, все safe_send)
"""
import os
import re
import json
import time
import random
import asyncio
import datetime
import platform
import sys
import threading
import traceback
from pathlib import Path
from collections import defaultdict, deque

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from flask import Flask
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("PYTHONUNBUFFERED", "1")

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


def data_path(name: str) -> Path:
    return DATA_DIR / name


UTC = datetime.UTC


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(UTC)


def log(msg: str):
    print(msg, flush=True)


# ============================================================
# НАСТРОЙКИ
# ============================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

LOG_CHANNEL_ID = 1511463623703265361
APPLICATION_LOGS_CHANNEL_ID = 1511463623703265361
APPLICATIONS_CHANNEL_ID = 1511463623703265361
THREADS_CHANNEL_ID = 1236678127778795660
DB_CHANNEL_ID = 1554883485834149888
ERROR_LOG_CHANNEL_ID = 1511463623703265361

ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", "0"))
REVIEWER_ROLE_ID_2 = int(os.getenv("REVIEWER_ROLE_ID_2", "0"))
SPAM_VOTE_ROLE_ID = int(os.getenv("SPAM_VOTE_ROLE_ID", "0"))
EXTRA_REVIEWER_ROLE_1 = int(os.getenv("EXTRA_REVIEWER_ROLE_1", "0"))
EXTRA_REVIEWER_ROLE_2 = int(os.getenv("EXTRA_REVIEWER_ROLE_2", "0"))
EXTRA_REVIEWER_ROLE_3 = int(os.getenv("EXTRA_REVIEWER_ROLE_3", "0"))

AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "0"))
BYPASS_ROLE_ID = int(os.getenv("BYPASS_ROLE_ID", "0"))
NO_COOLDOWN_ROLE_ID = int(os.getenv("NO_COOLDOWN_ROLE_ID", "0"))

ACTIVITY_ROLE_ID = int(os.getenv("ACTIVITY_ROLE_ID", "1448368118190837800"))

CLAN_NAME = os.getenv("CLAN_NAME", "TALENT")
CLAN_URL = os.getenv("CLAN_URL", "https://cs2red.ru/clans/id/47")
VOTES_REQUIRED = int(os.getenv("VOTES_REQUIRED", "2"))

ACTIVITY_GOAL_HOURS = 8
ACTIVITY_MIN_HOURS = 8
APPLY_EMBED_COLOR = 0x2B2D31

BOT_START_TIME = time.time()

CMD_API_TIMEOUT = 30.0

CS2RED_COOKIES = {k: v for k, v in {
    "token": os.getenv("CS2RED_TOKEN", ""),
    "bh": os.getenv("CS2RED_BH", ""),
    "_yasc": os.getenv("CS2RED_YASC", ""),
    "browser_id": os.getenv("CS2RED_BROWSER_ID", ""),
    "yandexuid": os.getenv("CS2RED_YANDEXUID", ""),
    "yuidss": os.getenv("CS2RED_YUIDSS", ""),
    "i": os.getenv("CS2RED_I", ""),
    "__ddg1_": os.getenv("CS2RED_DDG1", ""),
    "__ddg8_": os.getenv("CS2RED_DDG8", ""),
    "__ddg9_": os.getenv("CS2RED_DDG9", ""),
    "__ddg10_": os.getenv("CS2RED_DDG10", ""),
    "yabs-sid": os.getenv("CS2RED_YABS_SID", ""),
    "_ym_uid": os.getenv("CS2RED_YM_UID", ""),
    "_ym_d": os.getenv("CS2RED_YM_D", ""),
    "_ym_isad": os.getenv("CS2RED_YM_ISAD", ""),
    "ymex": os.getenv("CS2RED_YMEX", ""),
}.items() if v}

CS2RED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.6",
    "Referer": "https://cs2red.ru/admin",
    "Origin": "https://cs2red.ru",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
}

ROLE_MAP = {1: None, 2: "VIP", 3: "Premium", 4: "Moderator",
            5: "Администратор", 6: "Амбассадор", 9: "Plus"}
ROLE_DISPLAY_MAP = {1: "Мл. Модер", 3: "Модератор", 5: "Админ",
                    6: "С. Админ", 7: "Спонсор", 13: "Гл.Модератор"}


def role_display_name(role_id) -> str:
    return ROLE_DISPLAY_MAP.get(role_id) or ROLE_MAP.get(role_id) or "Игрок"


CLAN_ROLE_MAP = {
    47: 1448368118190837800, 108: 1555181110248476843, 95: 1454987841019838547,
    180: 1546232690288631909, 148: 1555181315874103406, 114: 1548957197659283456,
    155: 1555181474292965436, 272: 1524071629880168458, 61: 1555181722524717056,
    74: 1544421362431557732, 33: 1555181917756854355, 11: 1555182111349145600,
    8: 1555182240290443385, 367: 1555182697230504036, 160: 1555182823168544769,
    140: 1555182933264830524, 213: 1555183033131204719, 208: 1555183533180461126,
    12: 1555183608900358165, 38: 1555183705247588432, 196: 1555183791113510962,
    133: 1555183874605056080,
}

SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "15"))
REQUEST_DELAY = 0.3

ACTIVITY_TRACK_SECONDS = 300
ACTIVITY_TRACK_DELTA = 300
CLANS_CACHE_TTL = 300


# ============================================================
# ХРАНИЛИЩЕ JSON
# ============================================================
class JsonStore:
    def __init__(self, path, default):
        self.path = Path(path)
        self.default = default
        self.lock = asyncio.Lock()

    def _load(self):
        if not self.path.exists():
            return self.default() if callable(self.default) else self.default
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self.default() if callable(self.default) else self.default

    def _dump(self, data):
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def read(self):
        return self._load()

    async def get(self):
        async with self.lock:
            return self._load()

    async def save(self, data):
        async with self.lock:
            self._dump(data)

    async def update(self, fn):
        async with self.lock:
            data = self._load()
            result = fn(data)
            self._dump(data)
            return result


links_store = JsonStore(data_path("links.json"), dict)
players_store = JsonStore(data_path("players_db.json"), dict)
bans_store = JsonStore(data_path("users_db.json"), dict)
moders_store = JsonStore(data_path("moderators.json"), list)
votes_store = JsonStore(data_path("votes.json"), dict)
seen_store = JsonStore(data_path("seen.json"), dict)


def _write_error_to_file(context: str, exc):
    try:
        ts = now_utc().strftime("%Y-%m-%d %H:%M:%S")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) \
            if isinstance(exc, BaseException) else str(exc)
        with open(data_path("error_log.txt"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {context}\n{tb}\n{'=' * 60}\n")
    except Exception as e:
        log(f"⚠️ error_log: {e}")


NET_ERRORS = (
    aiohttp.ClientConnectorError,
    aiohttp.ClientOSError,
    aiohttp.ServerTimeoutError,
    asyncio.TimeoutError,
)


async def log_error(bot: commands.Bot, context: str, exc):
    _write_error_to_file(context, exc)
    log(f"❌ [{context}] {exc}")
    if isinstance(exc, NET_ERRORS):
        return
    channel = bot.get_channel(ERROR_LOG_CHANNEL_ID) if ERROR_LOG_CHANNEL_ID else None
    if channel is None:
        return
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) \
        if isinstance(exc, BaseException) else str(exc)
    try:
        await safe_send(channel, f"❌ **Ошибка**\n**Контекст:** `{context}`\n```\n{text[:1500]}\n```")
    except Exception as e:
        log(f"⚠️ не смог отправить лог: {e}")


# ============================================================
# ЗАЩИТА ОТ ФЛУДА (Cloudflare + Discord 429)
# ============================================================
_send_semaphore = asyncio.Semaphore(2)
_send_timestamps = deque()


async def _rate_limit_send():
    """Глобальный rate-limit: не более 3 сообщений в секунду."""
    async with _send_semaphore:
        now = time.time()
        while _send_timestamps and now - _send_timestamps[0] > 1.0:
            _send_timestamps.popleft()
        if len(_send_timestamps) >= 3:
            wait = 1.0 - (now - _send_timestamps[0])
            if wait > 0:
                await asyncio.sleep(wait)
        _send_timestamps.append(time.time())


async def safe_send(target, *args, retries: int = 5, **kwargs):
    """
    Отправка с retry. Уважает:
    - Discord 429 (rate-limit) — ждёт retry_after
    - Cloudflare 429 (HTML-заглушка) — ждёт 90 секунд
    """
    await _rate_limit_send()
    last_exc = None
    for attempt in range(retries):
        try:
            return await target.send(*args, **kwargs)
        except discord.HTTPException as e:
            last_exc = e
            if e.status == 429:
                is_cloudflare = False
                try:
                    body = await e.response.text()
                    if "cloudflare" in body.lower() or "access denied" in body.lower():
                        is_cloudflare = True
                except Exception:
                    pass

                if is_cloudflare:
                    wait = 90.0
                    log(f"🛡 Cloudflare 429 — жду {wait:.0f} сек (попытка {attempt + 1}/{retries})")
                else:
                    wait = getattr(e, "retry_after", None) or 5.0
                    log(f"⏱ Discord 429 — жду {wait:.1f} сек (попытка {attempt + 1}/{retries})")

                await asyncio.sleep(wait)
                continue

            if e.status >= 500 and attempt < retries - 1:
                await asyncio.sleep(3)
                continue
            raise
    log(f"❌ safe_send: не отправил после {retries} попыток: {last_exc}")
    return None


# ============================================================
# ГАРАНТИРОВАННОЕ ЗАКРЫТИЕ INTERACTION
# ============================================================
async def close_interaction(interaction: discord.Interaction, text: str = None,
                            ephemeral: bool = False):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=False)
        if text:
            await safe_send(interaction.followup, text, ephemeral=ephemeral)
    except discord.NotFound:
        pass
    except discord.HTTPException as e:
        log(f"⚠️ close_interaction: {e}")


async def run_with_timeout(coro, timeout: float, fallback_msg: str,
                           interaction: discord.Interaction,
                           context: str = ""):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        await log_error(bot, context or "run_with_timeout", "TIMEOUT")
        await close_interaction(interaction, fallback_msg, ephemeral=False)
        return None
    except Exception as e:
        await log_error(bot, context or "run_with_timeout", e)
        await close_interaction(interaction, f"❌ Ошибка: {str(e)[:200]}", ephemeral=False)
        return None


# ============================================================
# API: cs2red / Steam
# ============================================================
class API:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.sem = asyncio.Semaphore(4)
        self._clans_cache = {"ts": 0.0, "data": None}
        self.last_status: int | None = None

    async def start(self):
        connector = aiohttp.TCPConnector(
            family=2, ttl_dns_cache=300, limit=16,
            force_close=False, enable_cleanup_closed=True,
        )
        self.session = aiohttp.ClientSession(
            headers=CS2RED_HEADERS,
            cookies=CS2RED_COOKIES or None,
            timeout=aiohttp.ClientTimeout(total=20, connect=10),
            connector=connector,
        )
        log(f"🌐 API session. Cookies: {len(CS2RED_COOKIES)}, Headers: {len(CS2RED_HEADERS)}")

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_json(self, url, params=None):
        if not self.session:
            return None
        for attempt in range(2):
            try:
                async with self.sem:
                    async with self.session.get(url, params=params) as r:
                        self.last_status = r.status
                        if r.status == 403:
                            log(f"🔴 403 на {url}")
                            return None
                        if r.status == 429:
                            await asyncio.sleep(2)
                            continue
                        r.raise_for_status()
                        return await r.json(content_type=None)
            except NET_ERRORS as e:
                if attempt < 1:
                    await asyncio.sleep(1.5)
                    continue
                log(f"⚠️ GET {url}: сетевой сбой: {e}")
                return None
            except Exception as e:
                log(f"⚠️ GET {url}: {e}")
                return None
        return None

    async def cs2red_user(self, steam_id: str):
        data = await self._get_json(
            "https://cs2red.ru/api/admin/users",
            params={"begin": 0, "count": 1, "search": steam_id})
        if data is None:
            return None
        if not data.get("success"):
            return None
        users = data.get("users") or []
        if not users:
            return {"_not_found": True, "nick": None, "roleId": None}
        return users[0]

    async def cs2red_full_user(self, steam_id: str):
        user = await self.cs2red_user(steam_id)
        if not user or user.get("_not_found") or not user.get("id"):
            return None
        data = await self._get_json(
            "https://cs2red.ru/api/admin/user",
            params={"userId": user["id"]})
        if data and data.get("success"):
            return data.get("user")
        return None

    async def cs2red_clans(self):
        ts = asyncio.get_event_loop().time()
        if self._clans_cache["data"] is not None and ts - self._clans_cache["ts"] < CLANS_CACHE_TTL:
            return self._clans_cache["data"]
        data = await self._get_json("https://cs2red.ru/api/clans")
        if data is None:
            return None
        clans = data.get("clans") or []
        self._clans_cache = {"ts": ts, "data": clans}
        return clans

    async def player_clan(self, steam_id: str):
        user = await self.cs2red_user(steam_id)
        if not user or user.get("_not_found") or not user.get("id"):
            return None
        uid = int(user["id"])
        clans = await self.cs2red_clans()
        if clans is None:
            return None
        for clan in clans:
            for m in (clan.get("members") or []):
                if int(m.get("userId", 0) or 0) == uid:
                    return {"clan_id": clan.get("id"), "clan_name": clan.get("name"),
                            "clan_tag": clan.get("tag"), "member_role": m.get("roleId")}
        return None

    async def server_times(self) -> dict:
        data = await self._get_json("https://cs2red.ru/api/data/servers")
        result = {}
        for s in ((data or {}).get("servers") or []):
            raw = s.get("data")
            if not raw:
                continue
            try:
                d = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                continue
            for p in d.get("players", []):
                nick, t = p.get("nick"), p.get("time", 0)
                if nick:
                    result[nick] = max(result.get(nick, 0), t)
        return result

    async def _steam_get(self, iface: str, params: dict):
        key = os.getenv("STEAM_API_KEY")
        if not key:
            return None
        params["key"] = key
        params["steamids"] = params.pop("steam_id")
        return await self._get_json(f"https://api.steampowered.com/{iface}", params)

    async def steam_summary(self, steam_id: str):
        data = await self._steam_get("ISteamUser/GetPlayerSummaries/v2/", {"steam_id": steam_id})
        players = ((data or {}).get("response") or {}).get("players") or []
        return players[0] if players else None

    async def steam_bans(self, steam_id: str) -> dict:
        data = await self._steam_get("ISteamUser/GetPlayerBans/v1/", {"steam_id": steam_id})
        players = (data or {}).get("players") or []
        if not players:
            return {}
        p = players[0]
        return {"vac_banned": p.get("VACBanned", False),
                "number_of_vac_bans": p.get("NumberOfVACBans", 0),
                "days_since_last_ban": p.get("DaysSinceLastBan", 0),
                "community_banned": p.get("CommunityBanned", False),
                "number_of_game_bans": p.get("NumberOfGameBans", 0),
                "economy_ban": p.get("EconomyBan", "none")}


api = API()


# ============================================================
# ДОСТУП / ХЕЛПЕРЫ
# ============================================================
def is_moderator(user_id: int, guild: discord.Guild) -> bool:
    if user_id in moders_store.read():
        return True
    member = guild.get_member(user_id)
    return bool(member and member.guild_permissions.administrator)


def get_all_reviewer_role_ids() -> list:
    return [ALLOWED_ROLE_ID, REVIEWER_ROLE_ID_2, SPAM_VOTE_ROLE_ID,
            EXTRA_REVIEWER_ROLE_1, EXTRA_REVIEWER_ROLE_2, EXTRA_REVIEWER_ROLE_3]


def _has_any_role(member, role_ids) -> bool:
    return any(r.id in role_ids for r in member.roles)


def user_can_review(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_any_role(
        member, set(get_all_reviewer_role_ids()))


def user_can_spam_vote(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_any_role(
        member, {SPAM_VOTE_ROLE_ID})


def collect_reviewer_ids(guild: discord.Guild) -> set:
    ids = set()
    for rid in get_all_reviewer_role_ids():
        role = guild.get_role(rid) if rid else None
        if role:
            ids.update(m.id for m in role.members)
    ids.update(m.id for m in guild.members if m.guild_permissions.administrator)
    if guild.me:
        ids.add(guild.me.id)
    return ids


def is_user_blocked(discord_id: int):
    db = bans_store.read()
    entry = db.get(str(discord_id))
    if isinstance(entry, str) or not isinstance(entry, dict):
        return False, ""
    typ = entry.get("type", "temp")
    reason = entry.get("reason") or ""
    suffix = f" Причина: {reason}" if reason and reason != "-" else ""
    if typ == "perm":
        return True, "⛔ Вам **перманентно запрещено** подавать заявки." + suffix
    if typ == "temp":
        try:
            until = datetime.datetime.fromisoformat(entry.get("until"))
        except Exception:
            return False, ""
        now = now_utc()
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        if now < until:
            rem = until - now
            h, m = int(rem.seconds // 3600), int((rem.seconds % 3600) // 60)
            return True, f"🚫 Вам **запрещено** подавать заявки. Через **{h} ч. {m} мин.**" + suffix
        asyncio.ensure_future(bans_store.update(lambda d: d.pop(str(discord_id), None)))
    return False, ""


def _fmt_timestamp(ts):
    if not ts:
        return "-"
    if ts == 0:
        return "перманентно"
    try:
        return datetime.datetime.fromtimestamp(ts, UTC).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)


def build_activity_bar(hours: float, goal: float = 8.0, length: int = 10) -> str:
    ratio = max(0.0, min(1.0, hours / goal)) if goal > 0 else 0.0
    filled = int(round(ratio * length))
    if hours <= 0:
        e, s = "⚫", "Не играет"
    elif hours < goal * 0.25:
        e, s = "🔴", "Очень мало"
    elif hours < goal * 0.5:
        e, s = "🟠", "Мало"
    elif hours < goal * 0.75:
        e, s = "🟡", "Средне"
    elif hours < goal:
        e, s = "🟢", "Хорошо"
    elif hours == goal:
        e, s = "🟢", "Выполнено"
    else:
        e, s = "🟢", "Отлично"
    extra = f" (+{hours - goal:.1f} ч.)" if hours > goal else ""
    return f"`{'█' * filled}{'░' * (length - filled)}` {hours:.1f} / {goal:.0f} ч. - {e} {s}{extra}"


def get_player_activity(steam_id: str) -> float:
    entry = players_store.read().get(steam_id, {})
    a = entry.get("activity", {})
    if not isinstance(a, dict):
        return 0.0
    total = 0.0
    for h in a.values():
        try:
            total += float(h)
        except (ValueError, TypeError):
            continue
    return total


def extract_discord_id_from_embed(embed: discord.Embed) -> int:
    for f in embed.fields:
        if f.name == "Discord (упоминание)":
            m = re.search(r"\d{17,20}", f.value)
            if m:
                return int(m.group(0))
    return 0


# ============================================================
# ПРОФИЛЬ
# ============================================================
async def build_player_profile(guild, discord_id, steam_id=None):
    profile = {"discord_id": str(discord_id), "updated_at": now_utc().isoformat()}
    member = guild.get_member(discord_id)
    if member:
        profile["discord_name"] = member.display_name
        profile["discord_joined"] = member.joined_at.isoformat() if member.joined_at else None
    if not steam_id:
        steam_id = links_store.read().get(str(discord_id))
    if not steam_id:
        return profile
    profile["steamid64"] = steam_id
    user = await api.cs2red_user(steam_id)
    if user and not user.get("_not_found"):
        profile["cs2red_nick"] = user.get("nick", "-")
        profile["cs2red_role_id"] = user.get("roleId")
        profile["cs2red_role_name"] = role_display_name(user.get("roleId"))
    full = await api.cs2red_full_user(steam_id)
    if full:
        profile["cs2red_admins"] = full.get("admins", [])
        profile["cs2red_vips"] = full.get("vips", [])
        inner = full.get("user") or {}
        if inner:
            profile["cs2red_nick"] = inner.get("nick", profile.get("cs2red_nick"))
            profile["cs2red_role_id"] = inner.get("roleId", profile.get("cs2red_role_id"))
    profile["activity_hours"] = get_player_activity(steam_id)
    summ = await api.steam_summary(steam_id)
    if summ:
        profile["steam_avatar"] = summ.get("avatarfull")
        profile["steam_status"] = {0: "offline", 1: "online", 2: "busy", 3: "away"}.get(
            summ.get("personastate"), "unknown")
        profile["steam_nick"] = summ.get("personaname")
    sb = await api.steam_bans(steam_id)
    if sb:
        profile["steam_bans"] = sb
    return profile


async def send_player_report(bot, profile):
    channel = bot.get_channel(DB_CHANNEL_ID) if DB_CHANNEL_ID else None
    if not channel:
        log(f"⚠️ Канал {DB_CHANNEL_ID} не найден.")
        return
    embed = discord.Embed(title="👤 Профиль игрока", color=0x2B2D31, timestamp=now_utc())

    def field(name, value, inline=False):
        if value:
            embed.add_field(name=name, value=str(value)[:1024], inline=inline)

    if profile.get("discord_name"):
        field("Discord", f"{profile['discord_name']} (`{profile['discord_id']}`)")
    field("SteamID64", f"`{profile.get('steamid64')}`" if profile.get("steamid64") else None)
    field("Ник на cs2red", profile.get("cs2red_nick"))
    if profile.get("cs2red_role_name"):
        field("Роль на cs2red",
              f"{profile['cs2red_role_name']} (roleId={profile.get('cs2red_role_id')})")
    field("Ник в Steam", profile.get("steam_nick"))
    field("Статус Steam", profile.get("steam_status"))
    field("📝 Заметки", profile.get("notes"))
    field("📊 Активность за неделю",
          build_activity_bar(profile.get("activity_hours", 0.0), ACTIVITY_GOAL_HOURS))
    sb = profile.get("steam_bans", {})
    if sb:
        vl = ["❌ **VAC-бан**" if sb.get("vac_banned") else "✅ VAC-банов нет"]
        if sb.get("community_banned"):
            vl.append("❌ **Бан сообщества**")
        if sb.get("number_of_game_bans", 0) > 0:
            vl.append(f"❌ **Игровых банов**: {sb['number_of_game_bans']}")
        if sb.get("economy_ban") and sb["economy_ban"] != "none":
            vl.append(f"❌ **Economy**: {sb['economy_ban']}")
        field("🛡️ Steam-баны", "\n".join(vl))
    history = []
    if sb.get("vac_banned"):
        history.append("❌ VAC-бан")
    h = profile.get("activity_hours", 0.0)
    if h < ACTIVITY_MIN_HOURS:
        history.append(f"⚠️ Малоактивный ({h:.1f} ч. < {ACTIVITY_MIN_HOURS})")
    field("Итог", "\n".join(history) or "✅ Чист")
    admins = profile.get("cs2red_admins") or []
    if admins:
        lines = [f"👑 roleId={a.get('roleId', '-')} до "
                 f"{'перманентно' if a.get('expires', 0) == 0 else _fmt_timestamp(a.get('expires'))}"
                 for a in admins[:10]]
        if len(admins) > 10:
            lines.append(f"...и ещё {len(admins) - 10}")
        field(f"👑 Админ-права ({len(admins)})", "\n".join(lines))
    vips = [v for v in (profile.get("cs2red_vips") or [])
            if v.get("expires", 0) == 0 or v.get("expires", 0) >= int(now_utc().timestamp())]
    if vips:
        field(f"⭐ VIP ({len(vips)})",
              "\n".join(f"⭐ {v.get('group', '-')}" for v in vips[:10]))
    if profile.get("steam_avatar"):
        embed.set_thumbnail(url=profile["steam_avatar"])
    embed.set_footer(text=f"Обновлено: {profile.get('updated_at', '-')}")
    await safe_send(channel, embed=embed)


# ============================================================
# ЛОГИ
# ============================================================
async def _send(bot, channel_id, text):
    if not channel_id:
        return
    ch = bot.get_channel(channel_id)
    if ch:
        await safe_send(ch, text[:1900] + ("\n...(обрезано)" if len(text) > 1900 else ""))


async def log_to_channel(bot, text):
    if LOG_CHANNEL_ID:
        await _send(bot, LOG_CHANNEL_ID, text)


async def log_to_applications(bot, text):
    if APPLICATION_LOGS_CHANNEL_ID:
        await _send(bot, APPLICATION_LOGS_CHANNEL_ID, text)


def utc_stamp() -> str:
    return now_utc().strftime("%d.%m.%Y %H:%M")


# ============================================================
# СИНХРОНИЗАЦИЯ РОЛЕЙ
# ============================================================
async def sync_role_by_id(guild, member, steam_id):
    user = await api.cs2red_user(steam_id)
    if user is None:
        return f"⚠️ {member.display_name}: cs2red не ответил, роль не тронута"
    if user.get("_not_found"):
        tn = None
    else:
        tn = ROLE_MAP.get(user.get("roleId"))
    managed = {n for n in ROLE_MAP.values() if n}
    cur = {r for r in member.roles if r.name in managed}

    if tn is None:
        if cur:
            for r in cur:
                await member.remove_roles(r)
            return f"🔄 {member.display_name}: сняты"
        return f"ℹ️ {member.display_name}: без изменений"

    target = discord.utils.get(guild.roles, name=tn)
    if target is None:
        return f"⚠️ роль '{tn}' не найдена"

    if cur == {target}:
        return f"✅ {member.display_name}: уже '{tn}'"

    for r in cur:
        if r != target:
            await member.remove_roles(r)
    try:
        await member.add_roles(target)
        return f"✅ {member.display_name}: '{tn}'"
    except discord.Forbidden:
        return f"❌ нет прав"


async def sync_clan_role_by_id(guild, member, steam_id):
    if not CLAN_ROLE_MAP:
        return f"ℹ️ CLAN_ROLE_MAP пуст"

    user = await api.cs2red_user(steam_id)
    if user is None:
        return f"⚠️ {member.display_name}: cs2red не ответил, роли не тронуты"

    clans = await api.cs2red_clans()
    if clans is None:
        return f"⚠️ {member.display_name}: /api/clans не ответил, роли не тронуты"

    if not clans:
        return f"⚠️ {member.display_name}: /api/clans пусто, роли не тронуты"

    total_members = sum(len(c.get("members") or []) for c in clans)
    if total_members == 0:
        return f"⚠️ {member.display_name}: в /api/clans нет members, роли не тронуты"

    clan = await api.player_clan(steam_id)
    managed = set(CLAN_ROLE_MAP.values())
    held = [r for r in member.roles if r.id in managed]

    if clan is None:
        if held:
            for r in held:
                try:
                    await member.remove_roles(r)
                except discord.Forbidden:
                    pass
            return f"🔄 клан снят"
        return f"ℹ️ без клана"

    tid = CLAN_ROLE_MAP.get(clan["clan_id"])
    if tid is None:
        return f"ℹ️ клан без роли в CLAN_ROLE_MAP ({clan['clan_name']})"

    target = guild.get_role(tid)
    if target is None:
        return f"⚠️ роль {tid} не найдена"

    for r in held:
        if r.id != tid:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass

    if target in member.roles:
        return f"✅ уже в '{clan['clan_name']}'"
    try:
        await member.add_roles(target)
        return f"✅ выдан клан '{clan['clan_name']}'"
    except discord.Forbidden:
        return f"❌ нет прав"


# ============================================================
# ВЕТКИ ЗАЯВОК
# ============================================================
async def close_application_thread(thread, closed_by, reason):
    if not isinstance(thread, discord.Thread):
        return
    try:
        try:
            await safe_send(thread, f"🔒 **Ветка закрыта.** {reason}\n**Закрыл:** {closed_by.mention}")
        except Exception:
            pass
        await asyncio.sleep(5)
        try:
            await thread.edit(archived=True, locked=True, reason=f"Заявка {reason}")
        except Exception:
            pass
        keep = collect_reviewer_ids(thread.guild)
        try:
            members = await thread.fetch_members()
        except Exception:
            members = []
        for m in members:
            if m.id not in keep:
                try:
                    await thread.remove_user(m)
                except Exception:
                    pass
    except Exception as e:
        log(f"⚠️ close_thread: {e}")


# ============================================================
# ГОЛОСА
# ============================================================
def _get_votes(mid):
    return votes_store.read().get(str(mid)) or {"accept": 0, "deny": 0, "voters": []}


async def _save_votes(mid, st):
    await votes_store.update(lambda d: d.update({str(mid): st}))


async def _vote(interaction, kind):
    await interaction.response.defer()
    if not user_can_review(interaction.user):
        await safe_send(interaction.followup, "❌ Нет прав.", ephemeral=True)
        return
    st = _get_votes(interaction.message.id)
    if interaction.user.id in st["voters"] and not user_can_spam_vote(interaction.user):
        await safe_send(interaction.followup, "Вы уже голосовали.", ephemeral=True)
        return
    st[kind] += 1
    if interaction.user.id not in st["voters"]:
        st["voters"].append(interaction.user.id)
    await _save_votes(interaction.message.id, st)

    view = ApplicationManagement()
    view.update_labels(interaction.message.id)
    if st[kind] >= VOTES_REQUIRED:
        embed = interaction.message.embeds[0]
        status = "Принят" if kind == "accept" else "Отклонен"
        embed.set_footer(text=f"Quantum • Статус: {status}")
        for c in view.children:
            c.disabled = True
        try:
            await interaction.message.edit(embed=embed, view=view)
        except Exception:
            pass
        tid = extract_discord_id_from_embed(embed)
        member = interaction.guild.get_member(tid) if tid else None
        if kind == "accept" and member and AUTO_ROLE_ID:
            role_to_give = interaction.guild.get_role(AUTO_ROLE_ID)
            if role_to_give:
                try:
                    await member.add_roles(role_to_give)
                    await log_to_channel(interaction.client,
                        f"✅ Заявка принята. {member.mention} получил {role_to_give.mention}")
                except discord.Forbidden:
                    pass
        if member:
            await log_to_channel(interaction.client,
                f"{'✅' if kind == 'accept' else '❌'} {member.mention}")
        if isinstance(interaction.channel, discord.Thread):
            await close_application_thread(interaction.channel, interaction.user, status)
    else:
        try:
            await interaction.message.edit(view=view)
        except Exception:
            pass


# ============================================================
# МЕНЮ ЗАЯВКИ
# ============================================================
class ApplicationManagement(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def update_labels(self, mid):
        st = _get_votes(mid)
        for c in self.children:
            if c.custom_id == "accept_btn":
                c.label = f"Принять {st['accept']}/{VOTES_REQUIRED}"
            elif c.custom_id == "deny_btn":
                c.label = f"Отклонить {st['deny']}/{VOTES_REQUIRED}"
            elif c.custom_id == "voted_list_btn":
                c.label = f"👥 {len(st['voters'])}"

    @discord.ui.button(label="🙋 Взять", style=discord.ButtonStyle.primary,
                       custom_id="take_btn", row=0)
    async def take(self, i, b):
        await i.response.defer()
        if not user_can_review(i.user):
            await safe_send(i.followup, "❌", ephemeral=True)
            return
        await safe_send(i.followup, f"🙋 Взял {i.user.mention}.")
        b.disabled = True
        try:
            await i.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="Принять 0/2", style=discord.ButtonStyle.success,
                       custom_id="accept_btn", row=0)
    async def accept(self, i, b):
        await _vote(i, "accept")

    @discord.ui.button(label="Отклонить 0/2", style=discord.ButtonStyle.danger,
                       custom_id="deny_btn", row=0)
    async def deny(self, i, b):
        await _vote(i, "deny")

    @discord.ui.button(label="🚫 Выдать запрет", style=discord.ButtonStyle.secondary,
                       custom_id="tempban_btn", row=1)
    async def temp_ban(self, i, b):
        if not user_can_review(i.user):
            await i.response.send_message("❌", ephemeral=True)
            return
        tid = extract_discord_id_from_embed(i.message.embeds[0])
        if not tid:
            await i.response.send_message("❌ ID не найден", ephemeral=True)
            return
        await i.response.send_modal(TempBanModal(tid))

    @discord.ui.button(label="⛔ Перм. запрет", style=discord.ButtonStyle.danger,
                       custom_id="permban_btn", row=1)
    async def perm_ban(self, i, b):
        await i.response.defer()
        if not user_can_review(i.user):
            await safe_send(i.followup, "❌", ephemeral=True)
            return
        tid = extract_discord_id_from_embed(i.message.embeds[0])
        if not tid:
            await safe_send(i.followup, "❌", ephemeral=True)
            return
        await bans_store.update(lambda d: d.update({str(tid): {
            "type": "perm", "until": None, "reason": f"Выдал {i.user}"}}))
        await safe_send(i.followup, f"⛔ <@{tid}> перм. запрет")
        await log_to_channel(i.client, f"⛔ perm <@{tid}> от {i.user.mention}")

    @discord.ui.button(label="✅ Снять запрет", style=discord.ButtonStyle.success,
                       custom_id="unban_btn", row=1)
    async def unban(self, i, b):
        await i.response.defer()
        if not user_can_review(i.user):
            await safe_send(i.followup, "❌", ephemeral=True)
            return
        tid = extract_discord_id_from_embed(i.message.embeds[0])
        if not tid:
            await safe_send(i.followup, "❌", ephemeral=True)
            return
        r = await bans_store.update(lambda d: d.pop(str(tid), None))
        await safe_send(i.followup, f"✅ снят с <@{tid}>" if r is not None else "ℹ️ нет")
        if r is not None:
            await log_to_channel(i.client, f"✅ unban <@{tid}> от {i.user.mention}")

    @discord.ui.button(label="👥 0", style=discord.ButtonStyle.secondary,
                       custom_id="voted_list_btn", row=1)
    async def voted_list(self, i, b):
        st = _get_votes(i.message.id)
        if not st["voters"]:
            await i.response.send_message("Пусто", ephemeral=True)
            return
        await i.response.send_message("Голосовали: " + ", ".join(f"<@{u}>" for u in st["voters"]),
                                      ephemeral=True)


class TempBanModal(discord.ui.Modal, title="Запрет"):
    def __init__(self, tid):
        super().__init__()
        self.tid = tid
        self.hours = discord.ui.TextInput(label="Часов", default="12", max_length=6)
        self.reason = discord.ui.TextInput(label="Причина", required=False, max_length=200)
        self.add_item(self.hours)
        self.add_item(self.reason)

    async def on_submit(self, i):
        try:
            hours = int(self.hours.value.strip())
            if hours <= 0:
                raise ValueError
        except ValueError:
            await i.response.send_message("❌ число", ephemeral=True)
            return
        until = (now_utc() + datetime.timedelta(hours=hours)).isoformat()
        await bans_store.update(lambda d: d.update({str(self.tid): {
            "type": "temp", "until": until, "reason": self.reason.value.strip() or "-"}}))
        await i.response.send_message(f"🚫 <@{self.tid}> запрет на {hours} ч.")
        await log_to_channel(i.client, f"🚫 temp <@{self.tid}> {hours}ч от {i.user.mention}")

# ============================================================
# МОДАЛЬНОЕ ОКНО ЗАЯВКИ
# ============================================================
class QuestionnaireModal(discord.ui.Modal, title="Заявка в клан"):
    def __init__(self, clan_name):
        super().__init__()
        self.clan_name = clan_name
        self.nickname = discord.ui.TextInput(label="Ваш игровой никнейм")
        self.steam_input = discord.ui.TextInput(label="Steam-профиль (ссылка или SteamID64)")
        self.age = discord.ui.TextInput(label="Ваш возраст")
        self.time = discord.ui.TextInput(label="Время (по МСК)")
        self.reason = discord.ui.TextInput(label="Комментарий",
                                            style=discord.TextStyle.paragraph, required=False)
        for it in (self.nickname, self.steam_input, self.age, self.time, self.reason):
            self.add_item(it)

    async def on_submit(self, i):
        await i.response.defer(ephemeral=False)
        blocked, rt = is_user_blocked(i.user.id)
        if blocked:
            await safe_send(i.followup, rt, ephemeral=True)
            return
        m = re.search(r"\d{17}", self.steam_input.value.strip())
        sid = m.group(0) if m else None
        if sid:
            steam_url = f"https://steamcommunity.com/profiles/{sid}"
            cs2red_url = f"https://cs2red.ru/profile/{sid}"
            csstats_url = f"https://csstats.gg/player/{sid}"
            sid_d = f"`{sid}`"
        else:
            steam_url = cs2red_url = csstats_url = "https://cs2red.ru"
            sid_d = "`- не распознан -`"
        e = discord.Embed(title="ЗАЯВКА В КЛАН", color=APPLY_EMBED_COLOR)
        e.add_field(name="Игрок", value=self.nickname.value, inline=False)
        e.add_field(name="Steam", value=f"[перейти]({steam_url})", inline=False)
        e.add_field(name="Сайт", value=f"[перейти]({cs2red_url})", inline=False)
        e.add_field(name="csstats", value=f"[перейти]({csstats_url})", inline=False)
        e.add_field(name="Возраст", value=f"```\n{self.age.value}\n```", inline=False)
        e.add_field(name="Discord", value=f"```\n{i.user.name}\n```", inline=False)
        e.add_field(name="МСК", value=f"```\n{self.time.value}\n```", inline=False)
        if self.reason.value and self.reason.value.strip():
            e.add_field(name="Комментарий", value=f"```\n{self.reason.value}\n```", inline=False)
        e.add_field(name="SteamID", value=sid_d, inline=False)
        e.add_field(name="Discord (упоминание)", value=i.user.mention, inline=False)
        e.set_thumbnail(url=i.user.display_avatar.url)
        e.set_footer(text=f"{CLAN_NAME} • {utc_stamp()}")

        ch = i.guild.get_channel(APPLICATIONS_CHANNEL_ID) if APPLICATIONS_CHANNEL_ID else None
        if ch:
            try:
                view = ApplicationManagement()
                msg = await safe_send(ch, content=f"🔔 Новая заявка от {i.user.mention}",
                                      embed=e, view=view)
                if msg:
                    view.update_labels(msg.id)
                    await msg.edit(view=view)
            except Exception as ex:
                log(f"⚠️ Канал заявок: {ex}")

        await safe_send(i.followup, "✅ Ваша заявка отправлена на рассмотрение!", ephemeral=True)
        asyncio.create_task(_create_application_thread(i, e))


async def _create_application_thread(i, e):
    try:
        if not THREADS_CHANNEL_ID:
            return
        ch = i.guild.get_channel(THREADS_CHANNEL_ID)
        if ch is None:
            return
        t = await ch.create_thread(name=f"заявка-{i.user.name.lower()}"[:100],
                                   type=discord.ChannelType.private_thread,
                                   invitable=False, auto_archive_duration=1440)
        try:
            await t.add_user(i.user)
        except Exception:
            pass
        added, tasks_ = set(), []
        for rid in get_all_reviewer_role_ids():
            role = i.guild.get_role(rid) if rid else None
            if role:
                for m in role.members:
                    if m.id not in added and not m.bot:
                        added.add(m.id)
                        tasks_.append(t.add_user(m))
        for x in range(0, len(tasks_), 20):
            await asyncio.gather(*tasks_[x:x + 20], return_exceptions=True)
        view = ApplicationManagement()
        msg = await safe_send(t, content=f"{i.user.mention}, ваша заявка на рассмотрении.",
                              embed=e, view=view)
        if msg:
            view.update_labels(msg.id)
            await msg.edit(view=view)
    except Exception as ex:
        log(f"⚠️ Ветка: {ex}")


class ClanSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Выберите клан", min_values=1, max_values=1,
                         options=[discord.SelectOption(label=CLAN_NAME,
                                                        description=f"Клан {CLAN_NAME}")])

    async def callback(self, i):
        await i.response.send_modal(QuestionnaireModal(self.values[0]))


class ClanView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ClanSelect())


# ============================================================
# БОТ
# ============================================================
PUBLIC_COMMANDS = {"link", "unlink", "ping", "health", "lookup"}


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def interaction_check(self, i):
        cmd = getattr(i, "command", None)
        if cmd is None or cmd.name in PUBLIC_COMMANDS:
            return True
        if not is_moderator(i.user.id, i.guild) and not i.response.is_done():
            await i.response.send_message("❌ Нет доступа.", ephemeral=True)
            return False
        return True

    async def setup_hook(self):
        try:
            log("🔧 setup_hook: начало")
            await api.start()
            log("✅ API session ready")

            if not GUILD_ID:
                log("❌ GUILD_ID = 0 — синхронизация команд не выполнится!")
                return

            g = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=g)
            log(f"🔄 Синхронизация команд для guild {GUILD_ID}...")
            synced = await self.tree.sync(guild=g)
            log(f"✅ Команд синхронизировано: {len(synced)}")

            self.add_view(ApplicationManagement())
            log("✅ ApplicationManagement view добавлен")

            auto_sync.start()
            activity_tracker.start()
            log("✅ Все 2 фоновых задачи запущены")
        except Exception as e:
            log(f"❌ ОШИБКА в setup_hook: {type(e).__name__}: {e}")
            traceback.print_exc()
            raise

    async def close(self):
        await api.close()
        await super().close()


bot = MyBot()


@bot.tree.error
async def on_app_command_error(i, err):
    if isinstance(err, discord.app_commands.CheckFailure):
        msg = "❌ Нет доступа."
        try:
            if not i.response.is_done():
                await i.response.send_message(msg, ephemeral=True)
            else:
                await safe_send(i.followup, msg, ephemeral=True)
        except Exception:
            pass
        return
    await log_error(i.client, f"cmd:{i.command}", err)


@bot.event
async def on_ready():
    log(f"✅ Бот {bot.user} готов!")
    log(f"🆔 GUILD_ID: {GUILD_ID}")
    log(f"🍪 CS2RED cookies: {len(CS2RED_COOKIES)} шт.")
    log(f"📡 Guilds: {[g.name for g in bot.guilds]}")


def admin_only(i):
    return i.user.guild_permissions.administrator


async def _admin_guard(i):
    if not admin_only(i):
        await i.response.send_message("❌ Нужны права админа.", ephemeral=True)
        return False
    return True


# ============================================================
# КОМАНДЫ ПРИВЯЗКИ
# ============================================================
@bot.tree.command(name="link", description="Привязать SteamID")
@app_commands.describe(steam_id="SteamID64 (17 цифр)")
@app_commands.checks.cooldown(1, 30)
async def link(i, steam_id: str):
    if not (steam_id.isdigit() and len(steam_id) == 17 and steam_id.startswith("7656119")):
        await i.response.send_message("❌ Неверный SteamID.", ephemeral=True)
        return
    await i.response.defer(ephemeral=False)
    try:
        existing = links_store.read()
        owner = next((d for d, s in existing.items() if s == steam_id), None)
        if owner and int(owner) != i.user.id:
            await safe_send(i.followup, "❌ SteamID занят.", ephemeral=False)
            return

        u = await run_with_timeout(
            api.cs2red_user(steam_id),
            timeout=CMD_API_TIMEOUT,
            fallback_msg="⚠️ cs2red не ответил за 30 сек. Попробуй позже или проверь `/health`.",
            interaction=i,
            context="/link",
        )
        if u is None:
            return
        if u.get("_not_found"):
            await safe_send(i.followup, f"❌ Игрок `{steam_id}` не найден на cs2red.", ephemeral=False)
            return

        await links_store.update(lambda d: d.update({str(i.user.id): steam_id}))
        await safe_send(i.followup,
            f"✅ Привязано: `{steam_id}` (ник **{u.get('nick', '-')}**)",
            ephemeral=False
        )
        try:
            s1 = await sync_role_by_id(i.guild, i.user, steam_id)
            s2 = await sync_clan_role_by_id(i.guild, i.user, steam_id)
            await log_to_channel(i.client, f"🔗 /link - {s1}\n{s2}")
        except Exception as e:
            await log_error(i.client, "/link.sync", e)
    except Exception as e:
        await log_error(i.client, "/link", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="unlink", description="Отвязать SteamID")
async def unlink(i):
    await i.response.defer(ephemeral=False)
    try:
        rid = await links_store.update(lambda d: d.pop(str(i.user.id), None))
        if rid is None:
            await safe_send(i.followup, "ℹ️ Не привязан.", ephemeral=False)
            return
        managed_n = {n for n in ROLE_MAP.values() if n}
        managed_i = set(CLAN_ROLE_MAP.values())
        removed = []
        for r in i.user.roles:
            if r.name in managed_n or r.id in managed_i:
                try:
                    await i.user.remove_roles(r)
                    removed.append(r.name)
                except discord.Forbidden:
                    pass
        await safe_send(i.followup,
            f"✅ Отвязано. Снято: {', '.join(removed) if removed else 'нет'}",
            ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/unlink", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="sync_all", description="Синхронизировать всех")
async def sync_all(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=False)
    try:
        links = links_store.read()
        if not links:
            await safe_send(i.followup, "ℹ️ Пусто.", ephemeral=False)
            return
        res = []
        for did, sid in links.items():
            m = i.guild.get_member(int(did))
            if m is None:
                res.append(f"⚠️ {did}: нет")
                continue
            res.append(await sync_role_by_id(i.guild, m, sid))
            res.append(await sync_clan_role_by_id(i.guild, m, sid))
            await asyncio.sleep(REQUEST_DELAY)
        text = f"📊 {len(res)}\n\n" + "\n".join(res)
        await safe_send(i.followup, text[:1900], ephemeral=False)
        await log_to_channel(i.client, text)
    except Exception as e:
        await log_error(i.client, "/sync_all", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


async def linked_member_autocomplete(i, current):
    links = links_store.read()
    if not links:
        return []
    ch = []
    for did, sid in links.items():
        m = i.guild.get_member(int(did))
        if m is None:
            continue
        s = current.lower()
        if s and s not in m.display_name.lower() and s not in sid:
            continue
        ch.append(app_commands.Choice(name=f"{m.display_name} | {sid}", value=str(m.id)))
        if len(ch) >= 25:
            break
    return ch


# ============================================================
# /link_all
# ============================================================
@bot.tree.command(name="link_all", description="Массовая привязка из mass_links.json")
async def link_all(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=False)

    try:
        f = data_path("mass_links.json")
        if not f.exists():
            await safe_send(i.followup, "❌ Файл `mass_links.json` не найден.", ephemeral=False)
            return

        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                raise ValueError("должен быть JSON-объект")
        except json.JSONDecodeError as e:
            await safe_send(i.followup,
                f"❌ JSON повреждён: {e}\n"
                f"Проверь файл на https://jsonlint.com",
                ephemeral=False
            )
            return
        except Exception as e:
            await safe_send(i.followup, f"❌ Ошибка чтения: {e}", ephemeral=False)
            return

        total = len(data)
        log(f"📥 /link_all: {total} записей")

        added = []
        skip_not_sid = []
        no_member = []
        not_on_site = []
        already = []
        other = []

        processed = 0
        last_progress = 0

        for did, sid in data.items():
            sid = str(sid).strip()

            if not (did.isdigit() and 17 <= len(did) <= 20):
                other.append(f"`{did}`: не Discord ID")
                processed += 1
                continue

            if not (sid.isdigit() and len(sid) == 17 and sid.startswith("7656119")):
                skip_not_sid.append(f"`{did}`: не SteamID (`{sid}`)")
                processed += 1
                continue

            existing = links_store.read()
            if existing.get(str(did)) == sid:
                already.append(f"`{did}` → `{sid}`")
                processed += 1
                continue

            m = i.guild.get_member(int(did))
            if m is None:
                no_member.append(f"`{did}` ({sid})")
                processed += 1
                continue

            owner = next((d for d, s in existing.items() if s == sid), None)
            if owner and owner != str(did):
                other.append(f"{m.display_name}: SteamID занят <@{owner}>")
                processed += 1
                continue

            user = await api.cs2red_user(sid)
            if user is None or user.get("_not_found"):
                not_on_site.append(f"{m.display_name}: `{sid}`")
                processed += 1
                continue

            await links_store.update(lambda d: d.update({str(did): sid}))
            added.append(f"✅ {m.display_name} → `{sid}` (cs2red: {user.get('nick', '-')})")
            processed += 1

            if processed - last_progress >= 20:
                last_progress = processed
                try:
                    await safe_send(i.followup,
                        f"⏳ Прогресс: {processed}/{total}…",
                        ephemeral=False
                    )
                except Exception:
                    pass

            await asyncio.sleep(REQUEST_DELAY)

        text = (
            f"📊 **Массовая привязка**\n"
            f"✅ Добавлено: **{len(added)}**\n"
            f"ℹ️ Уже привязано: **{len(already)}**\n"
            f"⏭ Не SteamID (ники): **{len(skip_not_sid)}**\n"
            f"⚠️ Нет на сервере: **{len(no_member)}**\n"
            f"⚠️ Нет на cs2red: **{len(not_on_site)}**\n"
            f"⚠️ Прочее: **{len(other)}**\n\n"
        )
        if added:
            text += "**Последние добавленные:**\n" + "\n".join(added[-10:]) + "\n\n"
        if not_on_site:
            text += "**Нет на cs2red:**\n" + "\n".join(not_on_site[:10]) + "\n\n"
        if no_member:
            text += "**Нет на сервере:**\n" + "\n".join(no_member[:10]) + "\n\n"
        if other:
            text += "**Прочее:**\n" + "\n".join(other[:10])
        await safe_send(i.followup, text[:1900], ephemeral=False)
        await log_to_channel(i.client,
            f"📊 /link_all: +{len(added)} / уже {len(already)} / "
            f"не SID {len(skip_not_sid)} / нет на сервере {len(no_member)} / "
            f"нет на cs2red {len(not_on_site)} / прочее {len(other)}")
    except Exception as e:
        await log_error(i.client, "/link_all", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="export_members", description="Выгрузить привязки в mass_links.json")
async def export_members(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=False)
    try:
        links = links_store.read()
        if not links:
            await safe_send(i.followup, "ℹ️ Нет привязанных.", ephemeral=False)
            return
        valid = {}
        for did, sid in links.items():
            if isinstance(sid, str) and sid.isdigit() and len(sid) == 17 and sid.startswith("7656119"):
                valid[did] = sid
        try:
            with open(data_path("mass_links.json"), "w", encoding="utf-8") as f:
                json.dump(valid, f, ensure_ascii=False, indent=2)
        except Exception as e:
            await log_error(i.client, "/export_members.write", e)
            await safe_send(i.followup, f"❌ {e}", ephemeral=False)
            return
        await safe_send(i.followup,
            f"✅ Выгружено привязок: **{len(valid)}**",
            ephemeral=False
        )
        await log_to_channel(i.client, f"📤 /export_members — {len(valid)}")
    except Exception as e:
        await log_error(i.client, "/export_members", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# БАЗА ИГРОКОВ
# ============================================================
@bot.tree.command(name="player_info", description="База игрока")
@app_commands.describe(member="Участник Discord")
async def player_info(i, member: discord.Member):
    await i.response.defer(ephemeral=False)

    try:
        profile = await run_with_timeout(
            build_player_profile(i.guild, member.id),
            timeout=CMD_API_TIMEOUT,
            fallback_msg="⏱ Сбор профиля занял больше 30 сек. "
                         "Скорее всего cs2red или Steam не отвечают. "
                         "Попробуй `/health` — проверить состояние API.",
            interaction=i,
            context="/player_info",
        )
        if profile is None:
            return

        if not profile.get("steamid64"):
            await safe_send(i.followup, "❌ Нет SteamID", ephemeral=False)
            return

        def _merge(db):
            old = db.get(profile["steamid64"], {})
            for k in ("activity", "notes"):
                if k in old:
                    profile[k] = old[k]
            profile["activity_hours"] = get_player_activity(profile["steamid64"])
            db[profile["steamid64"]] = profile
            return None
        await players_store.update(_merge)

        await send_player_report(i.client, profile)

        await safe_send(i.followup,
            f"✅ Профиль **{member.display_name}** отправлен в <#{DB_CHANNEL_ID}>.",
            ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/player_info", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="player_note", description="Заметка к профилю")
@app_commands.describe(member="Участник Discord", note="Заметка")
async def player_note(i, member: discord.Member, note: str):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=False)
    try:
        sid = links_store.read().get(str(member.id))
        if not sid:
            await safe_send(i.followup, "❌ Нет SteamID", ephemeral=False)
            return

        async def _make():
            return await build_player_profile(i.guild, member.id, sid)
        profile = players_store.read().get(sid) or await _make()
        profile["notes"] = note
        profile["updated_at"] = now_utc().isoformat()
        await players_store.update(lambda d: d.update({sid: profile}))
        await safe_send(i.followup, f"✅ Заметка для {member.mention}", ephemeral=False)
        await send_player_report(i.client, profile)
    except Exception as e:
        await log_error(i.client, "/player_note", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="player_list", description="Вся база")
async def player_list(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=False)
    try:
        db = players_store.read()
        if not db:
            await safe_send(i.followup, "ℹ️ Пусто", ephemeral=False)
            return
        links = links_store.read()
        rev = {s: d for d, s in links.items()}
        lines = []
        for sid, p in db.items():
            nick = p.get("cs2red_nick") or p.get("discord_name") or sid
            fl = "❌VAC " if p.get("steam_bans", {}).get("vac_banned") else ""
            did = p.get("discord_id") or rev.get(sid)
            m = i.guild.get_member(int(did)) if did else None
            part = f" - {m.mention}" if m else (f" - `{did}`" if did else "")
            lines.append(f"{fl}`{sid}` - {nick}{part}")
        text = "📊 **База:**\n" + "\n".join(lines[:50])
        if len(lines) > 50:
            text += f"\n...и ещё {len(lines) - 50}"
        await safe_send(i.followup, text[:1900], ephemeral=False)
    except Exception as e:
        await log_error(i.client, "/player_list", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="lookup", description="Инфо об игроке")
async def lookup(i, member: discord.Member):
    await i.response.defer(ephemeral=False)
    try:
        sid = links_store.read().get(str(member.id))
        if not sid:
            await safe_send(i.followup, "❌ Не привязан", ephemeral=False)
            return
        u = await run_with_timeout(
            api.cs2red_user(sid),
            timeout=CMD_API_TIMEOUT,
            fallback_msg="⚠️ cs2red не ответил за 30 сек.",
            interaction=i,
            context="/lookup",
        )
        if u is None:
            return
        nick = u.get("nick", "-") if u and not u.get("_not_found") else "-"
        rid = u.get("roleId") if u and not u.get("_not_found") else None
        clan = await api.player_clan(sid)
        ct = f" (клан: {clan['clan_name']})" if clan else " (без клана)"
        await safe_send(i.followup,
            f"🎮 **{nick}**{ct}\n👤 {member.mention}\n`{sid}`\n"
            f"Роль: **{role_display_name(rid) if rid else '-'}**",
            ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/lookup", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# /ping
# ============================================================
@bot.tree.command(name="ping", description="Проверить, жив ли бот")
async def ping(i):
    await i.response.defer(ephemeral=False)
    ws = bot.latency * 1000
    up = int(time.time() - BOT_START_TIME)
    d, r = divmod(up, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    us = f"{up} сек." if up < 60 else (f"{m} мин. {s} сек." if up < 3600
                                        else (f"{h} ч. {m} мин." if up < 86400
                                              else f"{d} д. {h} ч."))
    status = "🟢 Отлично" if ws < 150 else ("🟡 Норма" if ws < 400 else "🟠 Высокая")
    e = discord.Embed(title="🏓 Pong!", color=0x2B2D31, timestamp=now_utc())
    e.add_field(name="Статус", value="✅ Бот жив", inline=False)
    e.add_field(name="⏱ Аптайм", value=f"`{us}`", inline=True)
    e.add_field(name="📡 WS", value=f"`{ws:.0f} мс`", inline=True)
    e.add_field(name="Связь", value=status, inline=False)
    e.add_field(name="🍪 Cookies", value=f"`{len(CS2RED_COOKIES)}`", inline=True)
    e.add_field(name="🆔 Guild", value=f"`{GUILD_ID}`", inline=True)
    e.add_field(name="Python",
                value=f"{platform.python_version()} • discord.py {discord.__version__}",
                inline=False)
    e.set_footer(text=f"Quantum • {utc_stamp()}")
    if bot.user:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    await safe_send(i.followup, embed=e, ephemeral=False)


# ============================================================
# /health
# ============================================================
@bot.tree.command(name="health", description="Проверить работу всех систем бота")
async def health(i: discord.Interaction):
    await i.response.defer(ephemeral=False)

    results = []
    ok_count = 0
    fail_count = 0

    def add(emoji, name, status, ok):
        nonlocal ok_count, fail_count
        results.append((emoji, name, status, ok))
        if ok:
            ok_count += 1
        else:
            fail_count += 1

    ws_ms = bot.latency * 1000
    add("🌐", "Discord WebSocket", f"`{ws_ms:.0f} мс`", ws_ms < 500)

    guild = i.guild
    if guild:
        add("🏠", "Guild",
            f"`{guild.name}` (`{guild.id}`), участников: `{guild.member_count}`", True)
    else:
        add("🏠", "Guild", "не найден", False)

    me = guild.me if guild else None
    if me and guild:
        needed = {
            "Manage Roles": me.guild_permissions.manage_roles,
            "Send Messages": me.guild_permissions.send_messages,
            "Embed Links": me.guild_permissions.embed_links,
            "Manage Threads": me.guild_permissions.manage_threads,
            "Read Message History": me.guild_permissions.read_message_history,
        }
        missing = [n for n, ok in needed.items() if not ok]
        if not missing:
            add("🔐", "Права бота", "все необходимые выданы ✅", True)
        else:
            add("🔐", "Права бота", f"❌ нет: {', '.join(missing)}", False)
    else:
        add("🔐", "Права бота", "не удалось получить", False)

    try:
        t0 = time.perf_counter()
        test = await api._get_json("https://cs2red.ru/api/admin/users",
                                   params={"begin": 0, "count": 1})
        dt = (time.perf_counter() - t0) * 1000
        if test is not None and test.get("success") is not None:
            add("🍪", "cs2red /admin/users",
                f"`{dt:.0f} мс`, cookies `{len(CS2RED_COOKIES)}` шт.", True)
        else:
            status = getattr(api, "last_status", "?")
            add("🍪", "cs2red /admin/users",
                f"❌ ответ `{status}`, cookies `{len(CS2RED_COOKIES)}` шт.", False)
    except Exception as e:
        add("🍪", "cs2red /admin/users", f"❌ {e}", False)

    try:
        t0 = time.perf_counter()
        clans_raw = await api._get_json("https://cs2red.ru/api/clans")
        dt = (time.perf_counter() - t0) * 1000
        if clans_raw and clans_raw.get("success"):
            clans = clans_raw.get("clans") or []
            total_members = sum(len(c.get("members") or []) for c in clans)
            if clans and total_members > 0:
                add("🏰", "cs2red /api/clans",
                    f"`{dt:.0f} мс`, кланов `{len(clans)}`, участников `{total_members}`",
                    True)
            else:
                add("🏰", "cs2red /api/clans",
                    f"⚠️ пусто: кланов `{len(clans)}`, members `{total_members}`", False)
        else:
            status = getattr(api, "last_status", "?")
            add("🏰", "cs2red /api/clans", f"❌ ответ `{status}`", False)
    except Exception as e:
        add("🏰", "cs2red /api/clans", f"❌ {e}", False)

    steam_key = os.getenv("STEAM_API_KEY")
    if not steam_key:
        add("🎮", "Steam API", "❌ ключ не задан", False)
    else:
        try:
            t0 = time.perf_counter()
            test = await api._steam_get("ISteamUser/GetPlayerBans/v1/",
                                        {"steam_id": "76561198000000000"})
            dt = (time.perf_counter() - t0) * 1000
            if test is not None:
                add("🎮", "Steam API", f"`{dt:.0f} мс`, ключ работает", True)
            else:
                add("🎮", "Steam API", "❌ не отвечает", False)
        except Exception as e:
            add("🎮", "Steam API", f"❌ {e}", False)

    for name, data in [
        ("links.json", links_store.read()),
        ("players_db.json", players_store.read()),
        ("users_db.json", bans_store.read()),
        ("moderators.json", moders_store.read()),
        ("votes.json", votes_store.read()),
        ("seen.json", seen_store.read()),
    ]:
        try:
            size = len(data) if hasattr(data, "__len__") else "?"
            add("📁", f"Файл `{name}`", f"записей: `{size}`", True)
        except Exception as e:
            add("📁", f"Файл `{name}`", f"❌ {e}", False)

    mass_file = data_path("mass_links.json")
    if mass_file.exists():
        try:
            with open(mass_file, "r", encoding="utf-8") as f:
                mass = json.load(f)
            total = len(mass)
            valid = sum(1 for k, v in mass.items()
                        if isinstance(v, str) and v.isdigit()
                        and len(v) == 17 and v.startswith("7656119"))
            add("📁", "Файл `mass_links.json`",
                f"всего `{total}`, валидных SteamID `{valid}`", True)
        except json.JSONDecodeError:
            add("📁", "Файл `mass_links.json`",
                "❌ JSON повреждён (проверь на jsonlint.com)", False)
        except Exception as e:
            add("📁", "Файл `mass_links.json`", f"❌ {e}", False)
    else:
        add("📁", "Файл `mass_links.json`", "⚠️ не найден", False)

    for name, task_obj, interval in [
        ("auto_sync", auto_sync, f"{SYNC_INTERVAL_MINUTES} мин"),
        ("activity_tracker", activity_tracker, f"{ACTIVITY_TRACK_SECONDS // 60} мин"),
    ]:
        if task_obj.is_running():
            nxt = task_obj.next_iteration
            if nxt:
                sec = max(0, int((nxt - now_utc()).total_seconds()))
                m_, s_ = divmod(sec, 60)
                next_str = f"{m_} мин. {s_} сек." if m_ else f"{s_} сек."
                add("⚙️", f"Задача `{name}`",
                    f"✅ работает, интервал {interval}, след. через `{next_str}`", True)
            else:
                add("⚙️", f"Задача `{name}`", f"✅ работает, интервал {interval}", True)
        else:
            add("⚙️", f"Задача `{name}`", "❌ не запущена", False)

    for name, cid in [
        ("LOG_CHANNEL_ID", LOG_CHANNEL_ID),
        ("DB_CHANNEL_ID", DB_CHANNEL_ID),
        ("APPLICATIONS_CHANNEL_ID", APPLICATIONS_CHANNEL_ID),
        ("THREADS_CHANNEL_ID", THREADS_CHANNEL_ID),
    ]:
        if not cid:
            add("📢", f"Канал `{name}`", "⚠️ не задан", False)
            continue
        ch = bot.get_channel(cid)
        if ch is None:
            add("📢", f"Канал `{name}`", f"❌ не найден (`{cid}`)", False)
        else:
            perm_ok = True
            if me:
                perm_ok = ch.permissions_for(me).send_messages
            add("📢", f"Канал `{name}`",
                f"`#{ch.name}` ({cid}), send: {'✅' if perm_ok else '❌'}", perm_ok)

    last_status = getattr(api, "last_status", None)
    add("📡", "Последний HTTP-статус cs2red",
        f"`{last_status}`" if last_status else "нет данных", last_status == 200)

    total_checks = ok_count + fail_count
    if fail_count == 0:
        color = 0x57F287
        title = "✅ Все системы работают"
    elif ok_count >= fail_count:
        color = 0xFEE75C
        title = f"⚠️ Работает: {ok_count}/{total_checks}, проблем: {fail_count}"
    else:
        color = 0xED4245
        title = f"❌ Проблем много: {fail_count} из {total_checks}"

    embed = discord.Embed(
        title=f"🩺 Проверка систем бота — {title}",
        description=(f"**Итог:** ✅ `{ok_count}` работает / ❌ `{fail_count}` проблем\n"
                     f"**Всего проверок:** `{total_checks}`"),
        color=color, timestamp=now_utc(),
    )
    for emoji, name, status, ok in results:
        arrow = "✅" if ok else "❌"
        embed.add_field(name=f"{emoji} {arrow} {name}", value=status[:1024], inline=False)

    if bot.user:
        embed.set_footer(text=f"Quantum • {utc_stamp()} (UTC)",
                         icon_url=bot.user.display_avatar.url)

    await safe_send(i.followup, embed=embed, ephemeral=False)
    await log_to_channel(i.client, f"🩺 /health: ✅ {ok_count} / ❌ {fail_count}")


# ============================================================
# МОДЕРАТОРЫ
# ============================================================
@bot.tree.command(name="moders", description="Список модераторов бота")
async def moders(i):
    await i.response.defer(ephemeral=False)
    try:
        mods = moders_store.read()
        if not mods:
            await safe_send(i.followup, "ℹ️ Пусто", ephemeral=False)
            return
        lines = [f"• {(i.guild.get_member(u).mention if i.guild.get_member(u) else f'`{u}`')}"
                 for u in mods]
        await safe_send(i.followup, f"🛠 ({len(mods)}):\n" + "\n".join(lines), ephemeral=False)
    except Exception as e:
        await log_error(i.client, "/moders", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="give", description="Выдать доступ")
async def give(i, user: discord.Member):
    if not admin_only(i):
        await i.response.send_message("❌", ephemeral=False)
        return
    await i.response.defer(ephemeral=False)
    try:
        added = await moders_store.update(
            lambda d: (d.append(user.id), True)[1] if user.id not in d else False)
        await safe_send(i.followup,
            f"✅ {user.mention} получил доступ." if added else "ℹ️ Уже есть.",
            ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/give", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="take", description="Забрать доступ")
async def take(i, user: discord.Member):
    if not admin_only(i):
        await i.response.send_message("❌", ephemeral=False)
        return
    await i.response.defer(ephemeral=False)
    try:
        removed = await moders_store.update(
            lambda d: (d.remove(user.id), True)[1] if user.id in d else False)
        await safe_send(i.followup,
            f"❌ {user.mention} лишён." if removed else "ℹ️ Уже без.",
            ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/take", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# АКТИВНОСТЬ
# ============================================================
def _get_steam_of(m):
    return links_store.read().get(str(m.id))


async def _activity_guard(i, m, need_admin=True):
    if need_admin and not admin_only(i):
        await i.response.send_message("❌", ephemeral=False)
        return None
    sid = _get_steam_of(m)
    if not sid:
        await i.response.send_message("❌ Нет SteamID", ephemeral=False)
        return None
    return sid


@bot.tree.command(name="activity_set", description="Установить часы активности")
async def activity_set(i, member: discord.Member, server: str, hours: float):
    sid = await _activity_guard(i, member)
    if not sid:
        return
    if hours < 0:
        await i.response.send_message("❌", ephemeral=False)
        return
    await i.response.defer(ephemeral=False)
    try:
        def _set(db):
            p = db.get(sid, {})
            a = p.get("activity", {})
            if not isinstance(a, dict):
                a = {}
            a[server.upper()] = float(hours)
            p.update(activity=a, discord_id=str(member.id),
                     discord_name=member.display_name, updated_at=now_utc().isoformat())
            db[sid] = p
            return sum(float(v) for v in a.values() if isinstance(v, (int, float)))
        total = await players_store.update(_set)
        await safe_send(i.followup,
            f"✅ {member.display_name} `{server.upper()}`: {hours} ч.\n"
            f"{build_activity_bar(total, ACTIVITY_GOAL_HOURS)}", ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/activity_set", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="activity_clear", description="Сбросить активность")
async def activity_clear(i, member: discord.Member):
    sid = await _activity_guard(i, member)
    if not sid:
        return
    await i.response.defer(ephemeral=False)
    try:
        await players_store.update(lambda db: db.update(
            {sid: {**db.get(sid, {}), "activity": {}, "updated_at": now_utc().isoformat()}}) or None)
        await safe_send(i.followup, "✅ Сброшено", ephemeral=False)
    except Exception as e:
        await log_error(i.client, "/activity_clear", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="activity_show", description="Активность игрока")
async def activity_show(i, member: discord.Member):
    sid = await _activity_guard(i, member, need_admin=False)
    if not sid:
        return
    await i.response.defer(ephemeral=False)
    try:
        a = players_store.read().get(sid, {}).get("activity", {})
        if not a:
            await safe_send(i.followup, "ℹ️ Пусто", ephemeral=False)
            return
        lines, t = [], 0.0
        for s, h in sorted(a.items()):
            try:
                hh = float(h)
            except (ValueError, TypeError):
                continue
            t += hh
            lines.append(f"• `{s}`: {hh} ч.")
        await safe_send(i.followup,
            f"📊 **{member.display_name}**\n" + "\n".join(lines)
            + f"\n\n{build_activity_bar(t, ACTIVITY_GOAL_HOURS)}", ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/activity_show", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="activity_all", description="Активность роли")
async def activity_all(i):
    await i.response.defer(ephemeral=False)
    try:
        role = i.guild.get_role(ACTIVITY_ROLE_ID) if ACTIVITY_ROLE_ID else None
        if role is None:
            await safe_send(i.followup, "❌ Роль не найдена", ephemeral=False)
            return
        ms = [m for m in role.members if not m.bot]
        if not ms:
            await safe_send(i.followup, "ℹ️ Пусто", ephemeral=False)
            return
        db, links = players_store.read(), links_store.read()
        data = []
        for m in ms:
            sid = links.get(str(m.id))
            h = 0.0
            if sid:
                a = db.get(sid, {}).get("activity", {})
                if isinstance(a, dict):
                    for v in a.values():
                        try:
                            h += float(v)
                        except (ValueError, TypeError):
                            pass
            data.append((m, h))
        data.sort(key=lambda x: x[1], reverse=True)
        body = "\n".join(f"{build_activity_bar(h, ACTIVITY_GOAL_HOURS)} - {m.mention}"
                         for m, h in data)
        done = sum(1 for _, h in data if h >= ACTIVITY_GOAL_HOURS)
        head = f"📊 **Роль {role.mention}**\n\n"
        foot = f"\n\n📈 Всего: {len(data)}\n✅ Выполнили: {done}\n⚠️ Малоактивных: {len(data) - done}"
        if len(head + body + foot) <= 2000:
            await safe_send(i.followup, head + body + foot, ephemeral=False)
        else:
            cut = body[:2000 - len(head) - len(foot) - 100]
            cut = cut[:cut.rfind("\n")]
            await safe_send(i.followup, head + cut + "\n_...обрезано_" + foot, ephemeral=False)
    except Exception as e:
        await log_error(i.client, "/activity_all", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# !setup — обновлённый текст
# ============================================================
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    e = discord.Embed(title="Официальные условия вступления в клан.",
                      color=0x36393F)
    e.description = (
        "Перед подачей заявки внимательно ознакомьтесь с нашими требованиями.\n"
        "**Несоответствие любому из пунктов приведёт к отказу.**\n\n"
        "**Общие требования:**\n"
        "• Отсутствие VAC-банов в Steam и блокировок на cs2red.ru.\n"
        "• Отсутствие членства в других кланах.\n"
        "• Возраст — **от 12 лет**.\n\n"
        f"**Требования для {CLAN_NAME}:**\n"
        "• Рейтинг — **от 1.000 ммр**.\n"
        "• Онлайн — **не менее 3 часов в день**.\n\n"
        "**Что указать в заявке:**\n"
        "• Steam-профиль (ссылку или SteamID64)\n\n"
        "**Важно!**\n"
        "Если вам не напишут в течение 7 дней — заявка отклоняется.\n"
        "После принятия есть **2 дня** на вступление.\n\n"
        "По вопросам вступления: обратитесь к администрации."
    )
    v = ClanView()
    v.add_item(discord.ui.Button(label=CLAN_NAME, url=CLAN_URL, row=1))
    await safe_send(ctx.channel, embed=e, view=v)


# ============================================================
# ФОНОВАЯ ЗАДАЧА: ТРЕКЕР АКТИВНОСТИ
# ============================================================
@tasks.loop(seconds=ACTIVITY_TRACK_SECONDS)
async def activity_tracker():
    try:
        links = links_store.read()
        if not links:
            return
        online = await api.server_times()
        if not online:
            return
        db = players_store.read()
        n2s = {p.get("cs2red_nick"): s for s, p in db.items() if p.get("cs2red_nick")}
        seen = seen_store.read()
        if not seen.pop("_seeded", None):
            for sid in links.values():
                if sid in n2s:
                    continue
                u = await api.cs2red_user(sid)
                if u and u.get("nick"):
                    n2s[u["nick"]] = sid
                    db.setdefault(sid, {})["cs2red_nick"] = u["nick"]
            await players_store.save(db)
        now = now_utc().isoformat()
        matched = 0
        for nick, secs in online.items():
            sid = n2s.get(nick)
            if not sid:
                continue
            prev = seen.get(nick)
            delta = (secs - prev) if prev is not None and secs >= prev else \
                (min(secs, ACTIVITY_TRACK_DELTA * 1.5) if prev is not None else 0.0)
            seen[nick] = secs
            if delta <= 0:
                continue
            p = db.get(sid, {})
            a = p.get("activity", {})
            if not isinstance(a, dict):
                a = {}
            a["AUTO"] = float(a.get("AUTO", 0)) + delta / 3600.0
            p.update(activity=a, discord_name=p.get("discord_name") or nick, updated_at=now)
            db[sid] = p
            matched += 1
        seen["_seeded"] = True
        if matched:
            await players_store.save(db)
            log(f"🕐 Трекер: +{matched}")
        await seen_store.save(seen)
    except Exception as e:
        await log_error(bot, "activity_tracker", e)


@activity_tracker.before_loop
async def before_activity_tracker():
    await bot.wait_until_ready()


# ============================================================
# АВТОСИНХРОНИЗАЦИЯ + 2 ЭМБЕДА
# ============================================================
def _short(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[:length - 1] + "…"


def _pad(text: str, length: int) -> str:
    text = _short(text, length)
    return text + " " * (length - len(text))


async def build_auto_sync_embeds(guild: discord.Guild) -> list:
    links = links_store.read()

    rows = []
    for did_str, sid in links.items():
        try:
            did = int(did_str)
        except ValueError:
            continue
        member = guild.get_member(did)
        if member is None:
            continue

        nick_cs2 = "-"
        clan_name = "—"
        try:
            user = await api.cs2red_user(sid)
            if user and not user.get("_not_found"):
                nick_cs2 = user.get("nick", "-")
            clan = await api.player_clan(sid)
            if clan:
                clan_name = clan.get("clan_name", "—")
        except Exception:
            pass

        rows.append((member.display_name, sid, nick_cs2, clan_name))

    rows.sort(key=lambda x: (x[3], x[0].lower()))

    W_DISC = 20
    W_STEAM = 17
    W_CLAN = 20

    header = (f"{_pad('Discord', W_DISC)} | "
              f"{_pad('SteamID', W_STEAM)} | "
              f"{_pad('Клан', W_CLAN)}")
    divider = "-" * W_DISC + "-+-" + "-" * W_STEAM + "-+-" + "-" * W_CLAN
    header_block = header + "\n" + divider

    MAX_PAGE_CHARS = 3200
    pages = []
    current_lines = []
    current_len = len(header_block)

    for disc, sid, nick_cs2, clan_name in rows:
        line = f"{_pad(disc, W_DISC)} | {_pad(sid, W_STEAM)} | {_pad(clan_name, W_CLAN)}"
        line_len = len(line) + 1
        if current_len + line_len > MAX_PAGE_CHARS and current_lines:
            pages.append(current_lines)
            current_lines = []
            current_len = len(header_block)
        current_lines.append(line)
        current_len += line_len

    if current_lines:
        pages.append(current_lines)

    if not pages:
        pages = [[]]

    embeds = []
    total_rows = len(rows)
    for idx, page in enumerate(pages):
        body = header_block
        if page:
            body += "\n" + "\n".join(page)
        else:
            body += "\n(нет привязанных игроков)"

        title = f"⏰ Автосинхронизация — {utc_stamp()} UTC"
        if len(pages) > 1:
            title += f" (стр. {idx + 1}/{len(pages)})"

        e = discord.Embed(title=title, description=f"```\n{body}\n```",
                          color=0x57F287, timestamp=now_utc())
        e.set_footer(text=f"Всего привязано: {total_rows}")
        embeds.append(e)

    not_linked = [m for m in guild.members
                  if not m.bot and str(m.id) not in links]
    not_linked.sort(key=lambda m: m.display_name.lower())

    if not_linked:
        nl_lines = [f"• {_short(m.display_name, 30)} (`{m.id}`)"
                    for m in not_linked[:100]]
        nl_text = "\n".join(nl_lines)
        if len(not_linked) > 100:
            nl_text += f"\n..._и ещё {len(not_linked) - 100}_"
        e2 = discord.Embed(title="🚫 Не авторизованы через /link",
                           description=nl_text[:4000], color=0x000000,
                           timestamp=now_utc())
        e2.set_footer(text=f"Всего без /link: {len(not_linked)}")
    else:
        e2 = discord.Embed(title="🚫 Не авторизованы через /link",
                           description="Все участники авторизованы ✅",
                           color=0x000000, timestamp=now_utc())

    embeds.append(e2)
    return embeds


@tasks.loop(minutes=SYNC_INTERVAL_MINUTES)
async def auto_sync():
    try:
        log(f"⏰ auto_sync {now_utc().isoformat()}")
        links = links_store.read()
        guild = bot.get_guild(GUILD_ID)
        if not links or guild is None:
            return

        for did, sid in links.items():
            m = guild.get_member(int(did))
            if m is None:
                continue
            try:
                await sync_role_by_id(guild, m, sid)
                await sync_clan_role_by_id(guild, m, sid)
            except Exception as e:
                await log_error(bot, f"auto_sync:{did}", e)
            await asyncio.sleep(REQUEST_DELAY)

        try:
            channel = bot.get_channel(LOG_CHANNEL_ID)
            if channel is not None:
                embeds = await build_auto_sync_embeds(guild)
                for emb in embeds:
                    try:
                        await safe_send(channel, embed=emb)
                    except Exception as e:
                        await log_error(bot, "auto_sync.report.embed", e)
                    await asyncio.sleep(2.0)
        except Exception as e:
            await log_error(bot, "auto_sync.report", e)

    except Exception as e:
        await log_error(bot, "auto_sync", e)


@auto_sync.error
async def auto_sync_error(err):
    await log_error(bot, "auto_sync.error", err)


@auto_sync.before_loop
async def before_auto_sync():
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(0, 120))


# ============================================================
# HTTP-СЕРВЕР ДЛЯ RENDER
# ============================================================
app = Flask(__name__)


@app.route("/")
def health():
    return "Bot is running"


def run_health_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        log("❌ DISCORD_TOKEN не задан!")
    elif GUILD_ID == 0:
        log("❌ GUILD_ID не задан!")
    else:
        threading.Thread(target=run_health_server, daemon=True).start()
        bot.run(DISCORD_TOKEN)
