"""
Quantum - бот клана (v9: диагностика + flush=True + защита ролей)
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

# Принудительный unbuffered вывод
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
    """Единый логгер с flush."""
    print(msg, flush=True)


# ============================================================
# НАСТРОЙКИ
# ============================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
APPLICATION_LOGS_CHANNEL_ID = int(os.getenv("APPLICATION_LOGS_CHANNEL_ID", "0"))
APPLICATIONS_CHANNEL_ID = int(os.getenv("APPLICATIONS_CHANNEL_ID", "0"))
THREADS_CHANNEL_ID = int(os.getenv("THREADS_CHANNEL_ID", "0"))
DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID", "0"))
ERROR_LOG_CHANNEL_ID = int(os.getenv("ERROR_LOG_CHANNEL_ID", str(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else "0"))

ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", "0"))
REVIEWER_ROLE_ID_2 = int(os.getenv("REVIEWER_ROLE_ID_2", "0"))
SPAM_VOTE_ROLE_ID = int(os.getenv("SPAM_VOTE_ROLE_ID", "0"))
EXTRA_REVIEWER_ROLE_1 = int(os.getenv("EXTRA_REVIEWER_ROLE_1", "0"))
EXTRA_REVIEWER_ROLE_2 = int(os.getenv("EXTRA_REVIEWER_ROLE_2", "0"))
EXTRA_REVIEWER_ROLE_3 = int(os.getenv("EXTRA_REVIEWER_ROLE_3", "0"))

AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "0"))
BYPASS_ROLE_ID = int(os.getenv("BYPASS_ROLE_ID", "0"))
NO_COOLDOWN_ROLE_ID = int(os.getenv("NO_COOLDOWN_ROLE_ID", "0"))

BANNED_ROLE_ID = int(os.getenv("BANNED_ROLE_ID", "0"))
MUTED_ROLE_ID = int(os.getenv("MUTED_ROLE_ID", "0"))
ACTIVITY_ROLE_ID = int(os.getenv("ACTIVITY_ROLE_ID", "0"))

CLAN_NAME = os.getenv("CLAN_NAME", "TALENT")
CLAN_URL = os.getenv("CLAN_URL", "https://cs2red.ru/clans/id/47")
VOTES_REQUIRED = int(os.getenv("VOTES_REQUIRED", "2"))

ACTIVITY_GOAL_HOURS = 8
ACTIVITY_MIN_HOURS = 8
APPLY_EMBED_COLOR = 0x2B2D31

AI_REPORT_CHANNEL_ID = int(os.getenv("AI_REPORT_CHANNEL_ID", "0"))
LLM7_BASE_URL = "https://api.llm7.io/v1"
LLM7_API_KEY = os.getenv("LLM7_API_KEY", "unused")
LLM7_MODEL = "default"
AI_ANALYSIS_INTERVAL_MINUTES = 60

AI_CHAT_HISTORY_SIZE = 6
AI_CHAT_MAX_TOKENS = 500
AI_CHAT_TIMEOUT = 25
AI_CHAT_MODEL = "fast"
AI_CHAT_COOLDOWN_SEC = int(os.getenv("AI_CHAT_COOLDOWN_SEC", "5"))

BOT_START_TIME = time.time()

# ============================================================
# CS2RED — 15 COOKIES
# ============================================================
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
BAN_CHECK_INTERVAL_HOURS = 24
MUTE_CHECK_INTERVAL_HOURS = 2
REQUEST_DELAY = 0.3

ACTIVITY_TRACK_SECONDS = 60
CLANS_CACHE_TTL = 300

AI_THINKING_PHRASES = [
    "⏳ Думаю…", "🤔 Секунду…", "💭 Подбираю ответ…", "✍️ Формулирую…",
    "🔍 Ищу ответ…", "🧠 Обрабатываю…", "⏱ Уже отвечаю…",
]

AI_CHAT_SYSTEM_PROMPTS = [
    ("Ты — дружелюбный и полезный ИИ-помощник Discord-сервера клана "
     f"{CLAN_NAME}. Отвечай кратко, по делу, на русском языке. "
     "Не выдумывай факты. Можно использовать markdown."),
    (f"Ты — ИИ-ассистент игрового клана {CLAN_NAME}. Помогаешь участникам "
     "Discord. Стиль — дружелюбный, но без воды. Язык ответа — как у вопроса."),
    ("Ты — сдержанный ИИ-помощник в Discord. Отвечай по существу, "
     "не выдумывай. Используй русский или язык собеседника."),
]


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
ai_stats_store = JsonStore(data_path("ai_stats.json"), dict)


# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================
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
# 429-ЗАЩИТА
# ============================================================
_send_semaphore = asyncio.Semaphore(5)
_send_timestamps = deque()


async def _rate_limit_send():
    async with _send_semaphore:
        now = time.time()
        while _send_timestamps and now - _send_timestamps[0] > 1.0:
            _send_timestamps.popleft()
        if len(_send_timestamps) >= 5:
            wait = 1.0 - (now - _send_timestamps[0])
            if wait > 0:
                await asyncio.sleep(wait)
        _send_timestamps.append(time.time())


async def safe_send(target, *args, retries: int = 3, **kwargs):
    await _rate_limit_send()
    last_exc = None
    for attempt in range(retries):
        try:
            return await target.send(*args, **kwargs)
        except discord.HTTPException as e:
            last_exc = e
            if e.status == 429:
                wait = getattr(e, "retry_after", None) or 5.0
                log(f"⏱ 429, жду {wait:.1f} сек (попытка {attempt + 1}/{retries})")
                await asyncio.sleep(wait + 0.5)
                continue
            if e.status >= 500 and attempt < retries - 1:
                await asyncio.sleep(3)
                continue
            raise
    log(f"❌ safe_send: не отправил после {retries} попыток: {last_exc}")
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
            timeout=aiohttp.ClientTimeout(total=25, connect=15),
            connector=connector,
        )
        log(f"🌐 API session started. Cookies: {len(CS2RED_COOKIES)}, Headers: {len(CS2RED_HEADERS)}")

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_json(self, url, params=None):
        if not self.session:
            return None
        for attempt in range(3):
            try:
                async with self.sem:
                    async with self.session.get(url, params=params) as r:
                        self.last_status = r.status
                        if r.status == 403:
                            log(f"🔴 403 Forbidden на {url} — cookies не приняты")
                            return None
                        if r.status == 429:
                            await asyncio.sleep(3)
                            continue
                        r.raise_for_status()
                        return await r.json(content_type=None)
            except NET_ERRORS as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                log(f"⚠️ GET {url}: сетевой сбой после 3 попыток: {e}")
                return None
            except Exception as e:
                log(f"⚠️ GET {url}: {e}")
                return None
        return None

    async def _get_html(self, url):
        if not self.session:
            return None
        for attempt in range(3):
            try:
                async with self.sem:
                    async with self.session.get(url) as r:
                        self.last_status = r.status
                        if r.status == 403:
                            log(f"🔴 403 Forbidden на {url}")
                            return None
                        if r.status != 200:
                            log(f"⚠️ GET {url}: статус {r.status}")
                            return None
                        return await r.text()
            except NET_ERRORS as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
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
        if not data or not data.get("success"):
            return None
        users = data.get("users") or []
        return users[0] if users else None

    async def cs2red_full_user(self, steam_id: str):
        user = await self.cs2red_user(steam_id)
        if not user or not user.get("id"):
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
        clans = (data or {}).get("clans") or []
        self._clans_cache = {"ts": ts, "data": clans}
        return clans

    async def player_clan(self, steam_id: str):
        user = await self.cs2red_user(steam_id)
        if not user or not user.get("id"):
            return None
        uid = int(user["id"])
        for clan in await self.cs2red_clans():
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
# LLM7
# ============================================================
class LLM7Client:
    def __init__(self, base_url: str = LLM7_BASE_URL, api_key: str = LLM7_API_KEY,
                 model: str = LLM7_MODEL, timeout: int = 25):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def start(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout))

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat(self, prompt: str, system: str | None = None,
                   history: list | None = None, model: str | None = None,
                   max_tokens: int = 500, temperature: float = 0.6,
                   timeout: int | None = None) -> str | None:
        if self._session is None or self._session.closed:
            await self.start()
        use_model = model or self.model
        use_timeout = timeout or self.timeout
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            messages.extend(history[-AI_CHAT_HISTORY_SIZE:])
        messages.append({"role": "user", "content": prompt})
        payload = {"model": use_model, "messages": messages,
                   "max_tokens": max_tokens, "temperature": temperature}
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        async with self._lock:
            elapsed = time.time() - self._last_call
            if elapsed < 1.1:
                await asyncio.sleep(1.1 - elapsed)
            for attempt in (1, 2):
                try:
                    async with self._session.post(
                        f"{self.base_url}/chat/completions",
                        json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=use_timeout),
                    ) as r:
                        self._last_call = time.time()
                        if r.status == 429:
                            log("⚠️ LLM7: rate-limit (429)")
                            return None
                        if r.status != 200:
                            body = await r.text()
                            log(f"⚠️ LLM7: статус {r.status}: {body[:200]}")
                            return None
                        data = await r.json(content_type=None)
                        try:
                            return data["choices"][0]["message"]["content"]
                        except (KeyError, IndexError, TypeError):
                            log(f"⚠️ LLM7: неожиданный ответ")
                            return None
                except asyncio.TimeoutError:
                    log(f"⚠️ LLM7: таймаут {use_timeout} сек")
                    if attempt == 2:
                        return None
                except Exception as e:
                    self._last_call = time.time()
                    log(f"⚠️ LLM7: ошибка: {e}")
                    return None
        return None


llm7 = LLM7Client()


async def ai_chat_with_fallback(prompt, system=None, history=None,
                                model="fast", max_tokens=500,
                                temperature=0.6, timeout=25):
    answer = await llm7.chat(prompt=prompt, system=system, history=history,
                             model=model, max_tokens=max_tokens,
                             temperature=temperature, timeout=timeout)
    if answer:
        return answer, "llm7"
    return None, "none"


ai_chat_history = defaultdict(lambda: deque(maxlen=AI_CHAT_HISTORY_SIZE))
ai_chat_locks = defaultdict(asyncio.Lock)
ai_last_call_by_user: dict[int, float] = {}


async def track_ai_usage(user_id: int, channel_id: int, ok: bool):
    ts = now_utc().isoformat()

    def _upd(d):
        d["total"] = int(d.get("total", 0)) + 1
        if ok:
            d["success"] = int(d.get("success", 0)) + 1
        else:
            d["fail"] = int(d.get("fail", 0)) + 1
        d["last_at"] = ts
        d["last_user"] = str(user_id)
        users = d.setdefault("users", {})
        users[str(user_id)] = int(users.get(str(user_id), 0)) + 1
        d["users"] = dict(sorted(users.items(), key=lambda kv: kv[1], reverse=True)[:20])
    await ai_stats_store.update(_upd)


# ============================================================
# ПАРСИНГ CS2RED (bans/mutes)
# ============================================================
async def check_punishment_via_html(steam_id: str, kind: str) -> bool:
    category = "MUTES" if kind == "mutes" else "BANS"
    html = await api._get_html(f"https://cs2red.ru/bans?category={category}")
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("a", href=f"/profile/{steam_id}")
    if not link:
        return False
    row = link
    for _ in range(10):
        row = row.parent
        if row is None:
            break
        cls = row.get("class") or []
        if "self-stretch" in cls and "h-16" in cls:
            break
    if row is None:
        return False
    txt = row.get_text(" ", strip=True)
    return not any(w in txt for w in ("Размучен", "Разбанен", "Снят"))


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
    if user:
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

    # 1) проверяем, что API жив
    user = await api.cs2red_user(steam_id)
    if user is None:
        return f"⚠️ {member.display_name}: cs2red не ответил, роли клана не тронуты"

    # 2) проверяем, что /api/clans тоже живой
    clans_raw = await api._get_json("https://cs2red.ru/api/clans")
    if not clans_raw or not clans_raw.get("success"):
        return f"⚠️ {member.display_name}: /api/clans не ответил, роли клана не тронуты"

    # 3) теперь точно можно принимать решения
    clan = await api.player_clan(steam_id)
    managed = set(CLAN_ROLE_MAP.values())
    held = [r for r in member.roles if r.id in managed]

    if clan is None:
        for r in held:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass
        return f"🔄 клан снят" if held else f"ℹ️ без клана"

    tid = CLAN_ROLE_MAP.get(clan["clan_id"])
    if tid is None:
        for r in held:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass
        return f"ℹ️ клан без роли ({clan['clan_name']})"

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
# БАНЫ / МУТЫ
# ============================================================
PUNISHMENTS = {
    "ban": {"endpoint": "bans", "role_id": BANNED_ROLE_ID, "emoji": "🔨", "word": "Бан"},
    "mute": {"endpoint": "mutes", "role_id": MUTED_ROLE_ID, "emoji": "🔇", "word": "Мут"},
}


async def check_punishment_roles(bot, guild, kind):
    cfg = PUNISHMENTS[kind]
    role = guild.get_role(cfg["role_id"]) if cfg["role_id"] else None
    if role is None:
        return [f"❌ Роль {cfg['role_id']} не найдена"]
    links = links_store.read()
    actions = []
    log(f"{cfg['emoji']} Проверка {kind} ({len(links)} игроков)...")
    for did, sid in list(links.items()):
        m = guild.get_member(int(did))
        if m is None:
            continue
        punished = await check_punishment_via_html(sid, cfg["endpoint"])
        has = role in m.roles
        if punished == has:
            continue
        try:
            if punished:
                await m.add_roles(role, reason=f"{cfg['word']} cs2red.ru")
                actions.append(f"{cfg['emoji']} + {m.display_name}")
            else:
                await m.remove_roles(role, reason=f"Снятие {cfg['word']}")
                actions.append(f"✅ − {m.display_name}")
            await log_to_applications(bot,
                f"{cfg['emoji']} **{cfg['word']}** {m.mention}\n🕒 {utc_stamp()}")
        except discord.Forbidden:
            actions.append(f"❌ нет прав для {m.display_name}")
        await asyncio.sleep(REQUEST_DELAY)
    return actions


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
        await i.response.defer(ephemeral=True)
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
        await safe_send(i.followup, "✅ Заявка отправлена!", ephemeral=True)
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
PUBLIC_COMMANDS = {"link", "unlink", "ping", "ai", "ai_reset"}


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
            await llm7.start()
            log("✅ LLM7 session ready")

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
            ban_check.start()
            mute_check.start()
            activity_tracker.start()
            ai_script_analysis.start()
            log("✅ Все 5 фоновых задач запущены")
        except Exception as e:
            log(f"❌ ОШИБКА в setup_hook: {type(e).__name__}: {e}")
            traceback.print_exc()
            raise

    async def close(self):
        await api.close()
        await llm7.close()
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
    log(f"🔑 LLM7_API_KEY: {'ЗАДАН' if LLM7_API_KEY and LLM7_API_KEY != 'unused' else 'unused'}")
    log(f"🍪 CS2RED cookies: {len(CS2RED_COOKIES)} шт.")
    log(f"📡 Guilds: {[g.name for g in bot.guilds]}")
    asyncio.create_task(_warmup_llm7())


async def _warmup_llm7():
    await asyncio.sleep(5)
    log("🔥 Прогрев LLM7...")
    for m in ("fast", "default"):
        try:
            r = await llm7.chat("ping", system="Ответь: pong", model=m,
                                max_tokens=10, timeout=40)
            log(f"🔥 [{m}]: {'OK' if r else 'FAIL'}")
            if r:
                break
        except Exception as e:
            log(f"⚠️ [{m}]: {e}")


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
    await i.response.defer(ephemeral=True)
    existing = links_store.read()
    owner = next((d for d, s in existing.items() if s == steam_id), None)
    if owner and int(owner) != i.user.id:
        await safe_send(i.followup, "❌ SteamID занят.", ephemeral=True)
        return
    u = await api.cs2red_user(steam_id)
    if u is None:
        await safe_send(i.followup,
            f"❌ Игрок `{steam_id}` не найден на cs2red. "
            f"Проверь: SteamID правильный? Cookies живые?",
            ephemeral=True)
        return
    await links_store.update(lambda d: d.update({str(i.user.id): steam_id}))
    await safe_send(i.followup,
        f"✅ Привязано: `{steam_id}` (ник **{u.get('nick', '-')}**)", ephemeral=True)
    try:
        s1 = await sync_role_by_id(i.guild, i.user, steam_id)
        s2 = await sync_clan_role_by_id(i.guild, i.user, steam_id)
        await log_to_channel(i.client, f"🔗 /link - {s1}\n{s2}")
    except Exception as e:
        await log_error(i.client, "/link", e)


@bot.tree.command(name="unlink", description="Отвязать SteamID")
async def unlink(i):
    await i.response.defer(ephemeral=True)
    rid = await links_store.update(lambda d: d.pop(str(i.user.id), None))
    if rid is None:
        await safe_send(i.followup, "ℹ️ Не привязан.", ephemeral=True)
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
        f"✅ Отвязано. Снято: {', '.join(removed) if removed else 'нет'}", ephemeral=True)


@bot.tree.command(name="sync_all", description="Синхронизировать всех")
async def sync_all(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=True)
    links = links_store.read()
    if not links:
        await safe_send(i.followup, "ℹ️ Пусто.", ephemeral=True)
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
    await safe_send(i.followup, text[:1900], ephemeral=True)
    await log_to_channel(i.client, text)


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


async def _check_single_punishment(i, m, kind):
    cfg = PUNISHMENTS[kind]
    role = i.guild.get_role(cfg["role_id"]) if cfg["role_id"] else None
    if role is None:
        await safe_send(i.followup, f"❌ Роль {cfg['role_id']} не найдена", ephemeral=True)
        return
    sid = links_store.read().get(str(m.id))
    if not sid:
        await safe_send(i.followup, f"❌ {m.mention} не привязан", ephemeral=True)
        return
    punished = await check_punishment_via_html(sid, "bans" if kind == "ban" else "mutes")
    has = role in m.roles
    if punished == has:
        await safe_send(i.followup,
            f"ℹ️ {m.display_name}: {'уже имеет роль' if has else 'чист'}", ephemeral=True)
        return
    try:
        if punished:
            await m.add_roles(role, reason=f"{cfg['word']} cs2red.ru")
            result = f"{cfg['emoji']} выдан"
        else:
            await m.remove_roles(role, reason=f"Снятие {cfg['word']}")
            result = "✅ снят"
        await safe_send(i.followup,
            f"**{cfg['word']} - {m.display_name}**\nSteamID: `{sid}`\n"
            f"Активно: **{'да' if punished else 'нет'}**\n{result}", ephemeral=True)
        await log_to_applications(i.client,
            f"{cfg['emoji']} {cfg['word']} {m.mention} от {i.user.mention}")
    except discord.Forbidden:
        await safe_send(i.followup, "❌ нет прав", ephemeral=True)


@bot.tree.command(name="check_bans", description="Проверить баны игрока")
@app_commands.autocomplete(member=linked_member_autocomplete)
async def check_bans(i, member: str):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=True)
    try:
        mid = int(member)
    except ValueError:
        await safe_send(i.followup, "❌ Некорректно", ephemeral=True)
        return
    t = i.guild.get_member(mid)
    if t is None:
        await safe_send(i.followup, "❌ Не найден", ephemeral=True)
        return
    await _check_single_punishment(i, t, "ban")


@bot.tree.command(name="check_mutes", description="Проверить муты игрока")
@app_commands.autocomplete(member=linked_member_autocomplete)
async def check_mutes(i, member: str):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=True)
    try:
        mid = int(member)
    except ValueError:
        await safe_send(i.followup, "❌ Некорректно", ephemeral=True)
        return
    t = i.guild.get_member(mid)
    if t is None:
        await safe_send(i.followup, "❌ Не найден", ephemeral=True)
        return
    await _check_single_punishment(i, t, "mute")


# ============================================================
# /link_all
# ============================================================
@bot.tree.command(name="link_all", description="Массовая привязка из mass_links.json")
async def link_all(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=True)

    f = data_path("mass_links.json")
    if not f.exists():
        await safe_send(i.followup, "❌ Файл `mass_links.json` не найден.", ephemeral=True)
        return

    try:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            raise ValueError("должен быть JSON-объект")
    except json.JSONDecodeError as e:
        await safe_send(i.followup,
            f"❌ JSON повреждён: {e}\n"
            f"Проверь файл на https://jsonlint.com — там нет закрывающей скобки "
            f"или пропущена запятая.", ephemeral=True)
        return
    except Exception as e:
        await safe_send(i.followup, f"❌ Ошибка чтения: {e}", ephemeral=True)
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
        if user is None:
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
                    f"⏳ Прогресс: {processed}/{total}…", ephemeral=True)
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
    await safe_send(i.followup, text[:1900], ephemeral=True)
    await log_to_channel(i.client,
        f"📊 /link_all: +{len(added)} / уже {len(already)} / "
        f"не SID {len(skip_not_sid)} / нет на сервере {len(no_member)} / "
        f"нет на cs2red {len(not_on_site)} / прочее {len(other)}")


@bot.tree.command(name="export_members", description="Выгрузить привязки в mass_links.json")
async def export_members(i):
    if not await _admin_guard(i):
        return
    await i.response.defer(ephemeral=True)
    links = links_store.read()
    if not links:
        await safe_send(i.followup, "ℹ️ Нет привязанных.", ephemeral=True)
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
        await safe_send(i.followup, f"❌ {e}", ephemeral=True)
        return
    await safe_send(i.followup, f"✅ Выгружено привязок: **{len(valid)}**", ephemeral=True)
    await log_to_channel(i.client, f"📤 /export_members — {len(valid)}")


# ============================================================
# БАЗА ИГРОКОВ
# ============================================================
@bot.tree.command(name="player_info", description="База игрока")
@app_commands.describe(member="Участник Discord")
async def player_info(i, member: discord.Member):
    await i.response.defer(ephemeral=True)
    try:
        profile = await build_player_profile(i.guild, member.id)
        if not profile.get("steamid64"):
            await safe_send(i.followup, "❌ Нет SteamID", ephemeral=True)
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
        await safe_send(i.followup, f"✅ Отправлено в <#{DB_CHANNEL_ID}>.", ephemeral=True)
    except Exception as e:
        await log_error(i.client, "/player_info", e)
        await safe_send(i.followup, f"❌ {e}", ephemeral=True)


@bot.tree.command(name="player_note", description="Заметка к профилю")
@app_commands.describe(member="Участник Discord", note="Заметка")
async def player_note(i, member: discord.Member, note: str):
    if not await _admin_guard(i):
        return
    sid = links_store.read().get(str(member.id))
    if not sid:
        await i.response.send_message("❌ Нет SteamID", ephemeral=True)
        return

    async def _make():
        return await build_player_profile(i.guild, member.id, sid)
    profile = players_store.read().get(sid) or await _make()
    profile["notes"] = note
    profile["updated_at"] = now_utc().isoformat()
    await players_store.update(lambda d: d.update({sid: profile}))
    await i.response.send_message(f"✅ Заметка для {member.mention}", ephemeral=True)
    await send_player_report(i.client, profile)


@bot.tree.command(name="player_list", description="Вся база")
async def player_list(i):
    if not await _admin_guard(i):
        return
    db = players_store.read()
    if not db:
        await i.response.send_message("ℹ️ Пусто", ephemeral=True)
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
    await i.response.send_message(text[:1900], ephemeral=True)


@bot.tree.command(name="lookup", description="Инфо об игроке")
async def lookup(i, member: discord.Member):
    await i.response.defer(ephemeral=True)
    sid = links_store.read().get(str(member.id))
    if not sid:
        await safe_send(i.followup, "❌ Не привязан", ephemeral=True)
        return
    u = await api.cs2red_user(sid)
    nick = u.get("nick", "-") if u else "-"
    rid = u.get("roleId") if u else None
    clan = await api.player_clan(sid)
    ct = f" (клан: {clan['clan_name']})" if clan else " (без клана)"
    await safe_send(i.followup,
        f"🎮 **{nick}**{ct}\n👤 {member.mention}\n`{sid}`\nРоль: **{role_display_name(rid) if rid else '-'}**",
        ephemeral=True)


# ============================================================
# /ping
# ============================================================
@bot.tree.command(name="ping", description="Проверить, жив ли бот")
async def ping(i):
    await i.response.defer(thinking=False)
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
    await safe_send(i.followup, embed=e)


# ============================================================
# /ai
# ============================================================
@bot.tree.command(name="ai", description="Спросить у ИИ")
@app_commands.describe(prompt="Вопрос", reset="Сбросить историю", long="Длинный ответ")
async def ai(i, prompt: str, reset: bool = False, long: bool = False):
    await i.response.defer(thinking=True)
    last = ai_last_call_by_user.get(i.user.id, 0.0)
    if not long and time.time() - last < AI_CHAT_COOLDOWN_SEC:
        await safe_send(i.followup,
            f"⏱ Подожди {AI_CHAT_COOLDOWN_SEC} сек. между запросами.", ephemeral=True)
        return
    ai_last_call_by_user[i.user.id] = time.time()
    cid = i.channel_id
    me = i.guild.me if i.guild else None
    if i.channel and me and not i.channel.permissions_for(me).send_messages:
        await safe_send(i.followup, "❌ Нет права писать", ephemeral=True)
        return
    if reset:
        ai_chat_history.pop(cid, None)
    hist = list(ai_chat_history.get(cid, []))
    if long:
        mt, to, mo = 1200, 60, "default"
    else:
        mt, to, mo = AI_CHAT_MAX_TOKENS, AI_CHAT_TIMEOUT, AI_CHAT_MODEL
    think = None
    try:
        think = await safe_send(i.followup, random.choice(AI_THINKING_PHRASES))
    except Exception:
        pass
    async with ai_chat_locks[cid]:
        ans, src = await ai_chat_with_fallback(
            prompt=prompt, system=random.choice(AI_CHAT_SYSTEM_PROMPTS),
            history=hist, model=mo, max_tokens=mt, temperature=0.6, timeout=to)
        if ans is None:
            if think:
                try:
                    await think.delete()
                except Exception:
                    pass
            await safe_send(i.followup, f"⚠️ ИИ не ответил за {to} сек.")
            await track_ai_usage(i.user.id, cid, False)
            return
        ai_chat_history[cid].append({"role": "user", "content": prompt})
        ai_chat_history[cid].append({"role": "assistant", "content": ans})
    if think:
        try:
            await think.delete()
        except Exception:
            pass
    await track_ai_usage(i.user.id, cid, True)
    chunks = [ans[j:j + 1900] for j in range(0, len(ans), 1900)] or ["(пусто)"]
    first = f"**{i.user.display_name} → /ai**\n{chunks[0]}"
    if len(first) > 2000:
        first = first[:1990] + "…"
    try:
        await safe_send(i.followup, first)
        for x in chunks[1:]:
            await safe_send(i.channel, x)
    except discord.Forbidden:
        await safe_send(i.followup, "❌ Нет прав", ephemeral=True)


@bot.tree.command(name="ai_reset", description="Сбросить историю /ai в канале")
async def ai_reset(i):
    ai_chat_history.pop(i.channel_id, None)
    await i.response.send_message("🧹 История /ai очищена.", ephemeral=False)


# ============================================================
# МОДЕРАТОРЫ
# ============================================================
@bot.tree.command(name="moders", description="Список модераторов бота")
async def moders(i):
    await i.response.defer(ephemeral=True)
    mods = moders_store.read()
    if not mods:
        await safe_send(i.followup, "ℹ️ Пусто", ephemeral=True)
        return
    lines = [f"• {(i.guild.get_member(u).mention if i.guild.get_member(u) else f'`{u}`')}"
             for u in mods]
    await safe_send(i.followup, f"🛠 ({len(mods)}):\n" + "\n".join(lines), ephemeral=True)


@bot.tree.command(name="give", description="Выдать доступ")
async def give(i, user: discord.Member):
    if not admin_only(i):
        await i.response.send_message("❌", ephemeral=True)
        return
    added = await moders_store.update(
        lambda d: (d.append(user.id), True)[1] if user.id not in d else False)
    await i.response.send_message(
        f"✅ {user.mention} получил доступ." if added else "ℹ️ Уже есть.", ephemeral=True)


@bot.tree.command(name="take", description="Забрать доступ")
async def take(i, user: discord.Member):
    if not admin_only(i):
        await i.response.send_message("❌", ephemeral=True)
        return
    removed = await moders_store.update(
        lambda d: (d.remove(user.id), True)[1] if user.id in d else False)
    await i.response.send_message(
        f"❌ {user.mention} лишён." if removed else "ℹ️ Уже без.", ephemeral=True)


# ============================================================
# АКТИВНОСТЬ
# ============================================================
def _get_steam_of(m):
    return links_store.read().get(str(m.id))


async def _activity_guard(i, m, need_admin=True):
    if need_admin and not admin_only(i):
        await i.response.send_message("❌", ephemeral=True)
        return None
    sid = _get_steam_of(m)
    if not sid:
        await i.response.send_message("❌ Нет SteamID", ephemeral=True)
        return None
    return sid


@bot.tree.command(name="activity_set", description="Установить часы активности")
async def activity_set(i, member: discord.Member, server: str, hours: float):
    sid = await _activity_guard(i, member)
    if not sid:
        return
    if hours < 0:
        await i.response.send_message("❌", ephemeral=True)
        return

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
    await i.response.send_message(
        f"✅ {member.display_name} `{server.upper()}`: {hours} ч.\n"
        f"{build_activity_bar(total, ACTIVITY_GOAL_HOURS)}", ephemeral=True)


@bot.tree.command(name="activity_clear", description="Сбросить активность")
async def activity_clear(i, member: discord.Member):
    sid = await _activity_guard(i, member)
    if not sid:
        return
    await players_store.update(lambda db: db.update(
        {sid: {**db.get(sid, {}), "activity": {}, "updated_at": now_utc().isoformat()}}) or None)
    await i.response.send_message("✅ Сброшено", ephemeral=True)


@bot.tree.command(name="activity_show", description="Активность игрока")
async def activity_show(i, member: discord.Member):
    sid = await _activity_guard(i, member, need_admin=False)
    if not sid:
        return
    a = players_store.read().get(sid, {}).get("activity", {})
    if not a:
        await i.response.send_message("ℹ️ Пусто", ephemeral=True)
        return
    lines, t = [], 0.0
    for s, h in sorted(a.items()):
        try:
            hh = float(h)
        except (ValueError, TypeError):
            continue
        t += hh
        lines.append(f"• `{s}`: {hh} ч.")
    await i.response.send_message(
        f"📊 **{member.display_name}**\n" + "\n".join(lines)
        + f"\n\n{build_activity_bar(t, ACTIVITY_GOAL_HOURS)}", ephemeral=True)


@bot.tree.command(name="activity_all", description="Активность роли")
async def activity_all(i):
    await i.response.defer()
    role = i.guild.get_role(ACTIVITY_ROLE_ID) if ACTIVITY_ROLE_ID else None
    if role is None:
        await safe_send(i.followup, "❌ Роль не найдена", ephemeral=True)
        return
    ms = [m for m in role.members if not m.bot]
    if not ms:
        await safe_send(i.followup, "ℹ️ Пусто", ephemeral=True)
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
        await safe_send(i.followup, head + body + foot)
    else:
        cut = body[:2000 - len(head) - len(foot) - 100]
        cut = cut[:cut.rfind("\n")]
        await safe_send(i.followup, head + cut + "\n_...обрезано_" + foot)


# ============================================================
# !setup
# ============================================================
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    e = discord.Embed(title="Условия вступления", color=0x36393F)
    e.description = ("**Общие требования:**\n• Нет VAC / блокировок cs2red\n"
                     "• Нет других кланов\n• Возраст от 12\n\n"
                     f"**Для {CLAN_NAME}:**\n• Рейтинг от 1.000 ммр\n• Онлайн ≥ 3 ч/день\n\n"
                     "**Важно:** Если не напишут за 7 дней — отказ.\n"
                     "После принятия 2 дня на вступление.")
    v = ClanView()
    v.add_item(discord.ui.Button(label=CLAN_NAME, url=CLAN_URL, row=1))
    await safe_send(ctx.channel, embed=e, view=v)


# ============================================================
# ФОНОВЫЕ ЗАДАЧИ
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
                (min(secs, ACTIVITY_TRACK_SECONDS * 1.5) if prev is not None else 0.0)
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


@tasks.loop(minutes=SYNC_INTERVAL_MINUTES)
async def auto_sync():
    try:
        log(f"⏰ auto_sync {now_utc().isoformat()}")
        links = links_store.read()
        guild = bot.get_guild(GUILD_ID)
        if not links or guild is None:
            return
        results = []
        for did, sid in links.items():
            m = guild.get_member(int(did))
            if m is None:
                continue
            try:
                results.append(await sync_role_by_id(guild, m, sid))
                results.append(await sync_clan_role_by_id(guild, m, sid))
            except Exception as e:
                await log_error(bot, f"auto_sync:{did}", e)
            await asyncio.sleep(REQUEST_DELAY)
        changes = [r for r in results if r.startswith(("✅", "🔄", "👥"))]
        if changes:
            await log_to_channel(bot, "⏰ **Автосинхронизация**\n" + "\n".join(changes[:30]))
    except Exception as e:
        await log_error(bot, "auto_sync", e)


@auto_sync.error
async def auto_sync_error(err):
    await log_error(bot, "auto_sync.error", err)


@tasks.loop(hours=BAN_CHECK_INTERVAL_HOURS)
async def ban_check():
    try:
        log(f"🔨 ban_check {now_utc().isoformat()}")
        g = bot.get_guild(GUILD_ID)
        if g is None:
            return
        a = await check_punishment_roles(bot, g, "ban")
        if a:
            await log_to_channel(bot, "🔨 **Баны:**\n" + "\n".join(a))
    except Exception as e:
        await log_error(bot, "ban_check", e)


@ban_check.error
async def ban_check_error(err):
    await log_error(bot, "ban_check.error", err)


@tasks.loop(hours=MUTE_CHECK_INTERVAL_HOURS)
async def mute_check():
    try:
        log(f"🔇 mute_check {now_utc().isoformat()}")
        g = bot.get_guild(GUILD_ID)
        if g is None:
            return
        a = await check_punishment_roles(bot, g, "mute")
        if a:
            await log_to_channel(bot, "🔇 **Муты:**\n" + "\n".join(a))
    except Exception as e:
        await log_error(bot, "mute_check", e)


@mute_check.error
async def mute_check_error(err):
    await log_error(bot, "mute_check.error", err)


async def _align_to_half_hour(minutes):
    await bot.wait_until_ready()
    now = now_utc()
    tm = 0 if minutes == 0 else 30
    target = now.replace(minute=tm, second=0, microsecond=0) if now.minute < tm \
        else (now + datetime.timedelta(hours=1)).replace(minute=tm, second=0, microsecond=0)
    w = (target - now).total_seconds()
    if w > 0:
        await asyncio.sleep(w)


async def before_ban_check():
    await _align_to_half_hour(0)


async def before_mute_check():
    await _align_to_half_hour(30)


ban_check.before_loop(before_ban_check)
mute_check.before_loop(before_mute_check)


@auto_sync.before_loop
async def before_auto_sync():
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(0, 120))


# ============================================================
# ИИ-АНАЛИЗ
# ============================================================
AI_SYSTEM_PROMPT = (
    "Ты — технический аналитик Discord-бота. Оцени роботизированность бота "
    "0-10, укажи 3 риска, 3-4 улучшения, итог. Кратко, не более 900 токенов."
)

_FIRST_AI_REPORT_DONE = False


def _collect_runtime_stats():
    links = links_store.read()
    players = players_store.read()
    bans = bans_store.read()
    mods = moders_store.read()
    votes = votes_store.read()
    ai_st = ai_stats_store.read()
    now = now_utc()
    atb, pb = 0, 0
    for e in bans.values():
        if not isinstance(e, dict):
            continue
        if e.get("type") == "perm":
            pb += 1
        elif e.get("type") == "temp":
            try:
                u = datetime.datetime.fromisoformat(e.get("until") or "")
                if u.tzinfo is None:
                    u = u.replace(tzinfo=UTC)
                if u > now:
                    atb += 1
            except Exception:
                pass
    g = bot.get_guild(GUILD_ID) if GUILD_ID else None
    total_h, act_pl = 0.0, 0
    for p in players.values():
        a = p.get("activity") if isinstance(p, dict) else None
        if isinstance(a, dict) and a:
            act_pl += 1
            for v in a.values():
                try:
                    total_h += float(v)
                except (TypeError, ValueError):
                    pass
    return {
        "uptime_sec": int(time.time() - BOT_START_TIME),
        "ws_latency_ms": round(bot.latency * 1000, 1),
        "guild_members": g.member_count if g else 0,
        "linked_users": len(links),
        "players_in_db": len(players),
        "active_players": act_pl,
        "total_tracked_hours": round(total_h, 2),
        "moderators_count": len(mods),
        "votes_records": len(votes),
        "perm_bans": pb,
        "active_temp_bans": atb,
        "ai_total": int(ai_st.get("total", 0)),
        "ai_success": int(ai_st.get("success", 0)),
        "ai_fail": int(ai_st.get("fail", 0
