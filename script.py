"""
Quantum - бот клана (v3: улучшения из ИИ-отчёта)
- HTTP-сервер для Render
- /link, /unlink, /ping, /ai, /ai_reset
- /ai — ИИ через LLM7.io (без Groq), вариативные фразы, кулдаун
- /check_bans, /check_mutes — автодополнение по привязанным
- Парсинг HTML cs2red.ru для банов/мутов
- Автосинхронизация ролей (15 мин), проверка наказаний, трекер активности
- Ежечасный ИИ-анализ работы бота в отдельный канал
- Логирование ошибок в файл + отдельный канал
- Мониторинг активности /ai
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

load_dotenv()

# ============================================================
# ПАПКА ДАННЫХ
# ============================================================
DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


def data_path(name: str) -> Path:
    return DATA_DIR / name


UTC = datetime.UTC


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(UTC)


# ============================================================
# НАСТРОЙКИ
# ============================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

LOG_CHANNEL_ID = 1555204495682568202
APPLICATION_LOGS_CHANNEL_ID = 1511463623703265361
APPLICATIONS_CHANNEL_ID = 1511463623703265361
THREADS_CHANNEL_ID = 1236678127778795660
DB_CHANNEL_ID = 1554883485834149888

# Улучшение №4 — отдельный канал для ошибок (fallback на лог-канал)
ERROR_LOG_CHANNEL_ID = int(os.getenv("ERROR_LOG_CHANNEL_ID", str(LOG_CHANNEL_ID)))

ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", "0"))
REVIEWER_ROLE_ID_2 = 1554631801937600603
SPAM_VOTE_ROLE_ID = 1396606001188175922
EXTRA_REVIEWER_ROLE_1 = 1447953747161387131
EXTRA_REVIEWER_ROLE_2 = 1524071237796626523
EXTRA_REVIEWER_ROLE_3 = 1378326630031818802

AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "0"))
BYPASS_ROLE_ID = int(os.getenv("BYPASS_ROLE_ID", "0"))
NO_COOLDOWN_ROLE_ID = 1554633825311654048

BANNED_ROLE_ID = 1554791570161668218
MUTED_ROLE_ID = 1554821496650862632
ACTIVITY_ROLE_ID = 1448368118190837800

CLAN_NAME = os.getenv("CLAN_NAME", "TALENT")
CLAN_URL = os.getenv("CLAN_URL", "https://cs2red.ru/clans/id/47")
VOTES_REQUIRED = int(os.getenv("VOTES_REQUIRED", "2"))

ACTIVITY_GOAL_HOURS = 8
ACTIVITY_MIN_HOURS = 8
APPLY_EMBED_COLOR = 0x2B2D31

# --- AI / LLM7 ---
AI_REPORT_CHANNEL_ID = 1554796338661826660
LLM7_BASE_URL = "https://api.llm7.io/v1"
LLM7_API_KEY = os.getenv("LLM7_API_KEY", "unused")
LLM7_MODEL = "default"
AI_ANALYSIS_INTERVAL_MINUTES = 60

AI_CHAT_HISTORY_SIZE = 6
AI_CHAT_MAX_TOKENS = 500
AI_CHAT_TIMEOUT = 25
AI_CHAT_MODEL = "fast"
# Улучшение №3 — кулдаун на /ai
AI_CHAT_COOLDOWN_SEC = int(os.getenv("AI_CHAT_COOLDOWN_SEC", "5"))

BOT_START_TIME = time.time()

CS2RED_COOKIES = {k: v for k, v in {
    "token": os.getenv("CS2RED_TOKEN", ""),
    "bh": os.getenv("CS2RED_BH", ""),
    "_yasc": os.getenv("CS2RED_YASC", ""),
    "browser_id": os.getenv("CS2RED_BROWSER_ID", ""),
    "yandexuid": os.getenv("CS2RED_YANDEXUID", ""),
}.items() if v}

CS2RED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.6",
    "Referer": "https://cs2red.ru/",
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

# Улучшение №1 — увеличено с 5 до 15 минут
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "15"))
BAN_CHECK_INTERVAL_HOURS = 24
MUTE_CHECK_INTERVAL_HOURS = 2
REQUEST_DELAY = 1.0

ACTIVITY_TRACK_SECONDS = 60
CLANS_CACHE_TTL = 300

# Улучшение №2 — вариативные фразы для /ai
AI_THINKING_PHRASES = [
    "⏳ Думаю…",
    "🤔 Секунду…",
    "💭 Подбираю ответ…",
    "✍️ Формулирую…",
    "🔍 Ищу ответ…",
    "🧠 Обрабатываю…",
    "⏱ Уже отвечаю…",
]

AI_CHAT_SYSTEM_PROMPTS = [
    ("Ты — дружелюбный и полезный ИИ-помощник Discord-сервера клана "
     f"{CLAN_NAME}. Отвечай кратко, по делу, на русском языке. "
     "Если пользователь пишет на другом языке — отвечай на его языке. "
     "Не выдумывай факты. Можно использовать markdown."),
    (f"Ты — ИИ-ассистент игрового клана {CLAN_NAME}. Помогаешь участникам "
     "Discord: отвечаешь на вопросы, объясняешь, подсказываешь. "
     "Стиль — дружелюбный, но без воды. Язык ответа — как у вопроса. "
     "Markdown разрешён."),
    ("Ты — сдержанный ИИ-помощник в Discord. Отвечай по существу, "
     "не выдумывай. Если чего-то не знаешь — честно скажи. "
     "Используй русский или язык собеседника. Форматируй ответы "
     "markdown-ом, если это уместно."),
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
# Улучшение №3 — статистика /ai
ai_stats_store = JsonStore(data_path("ai_stats.json"), dict)


# ============================================================
# УЛУЧШЕНИЕ №4 — ЛОГИРОВАНИЕ ОШИБОК
# ============================================================
_error_log_lock = asyncio.Lock()


def _write_error_to_file(context: str, exc):
    """Пишет ошибку в error_log.txt рядом с ботом."""
    try:
        ts = now_utc().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(exc, BaseException):
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        else:
            tb = str(exc)
        with open(data_path("error_log.txt"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {context}\n{tb}\n{'=' * 60}\n")
    except Exception as e:
        print(f"⚠️ error_log: {e}")


async def log_error(bot: commands.Bot, context: str, exc):
    """Пишет ошибку в файл и в канал ошибок."""
    _write_error_to_file(context, exc)
    print(f"❌ [{context}] {exc}")

    channel = bot.get_channel(ERROR_LOG_CHANNEL_ID)
    if channel is None:
        return
    if isinstance(exc, BaseException):
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    else:
        text = str(exc)
    try:
        await channel.send(
            f"❌ **Ошибка**\n**Контекст:** `{context}`\n"
            f"```\n{text[:1500]}\n```"
        )
    except Exception as e:
        print(f"⚠️ Не смог отправить лог ошибки: {e}")


# ============================================================
# API: cs2red / Steam
# ============================================================
class API:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.sem = asyncio.Semaphore(4)
        self._clans_cache = {"ts": 0.0, "data": None}

    async def start(self):
        self.session = aiohttp.ClientSession(
            headers=CS2RED_HEADERS,
            cookies=CS2RED_COOKIES or None,
            timeout=aiohttp.ClientTimeout(total=20),
        )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_json(self, url, params=None):
        if not self.session:
            return None
        async with self.sem:
            try:
                async with self.session.get(url, params=params) as r:
                    if r.status in (403, 429):
                        return None
                    r.raise_for_status()
                    return await r.json(content_type=None)
            except Exception as e:
                await log_error(bot, f"GET {url}", e)
                return None

    async def _get_html(self, url):
        if not self.session:
            return None
        async with self.sem:
            try:
                async with self.session.get(url) as r:
                    if r.status != 200:
                        await log_error(bot, f"GET {url}", f"статус {r.status}")
                        return None
                    return await r.text()
            except Exception as e:
                await log_error(bot, f"GET {url}", e)
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
                    return {
                        "clan_id": clan.get("id"),
                        "clan_name": clan.get("name"),
                        "clan_tag": clan.get("tag"),
                        "member_role": m.get("roleId"),
                    }
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
        data = await self._steam_get(
            "ISteamUser/GetPlayerSummaries/v2/",
            {"steam_id": steam_id})
        players = ((data or {}).get("response") or {}).get("players") or []
        return players[0] if players else None

    async def steam_bans(self, steam_id: str) -> dict:
        data = await self._steam_get(
            "ISteamUser/GetPlayerBans/v1/", {"steam_id": steam_id})
        players = (data or {}).get("players") or []
        if not players:
            return {}
        p = players[0]
        return {
            "vac_banned": p.get("VACBanned", False),
            "number_of_vac_bans": p.get("NumberOfVACBans", 0),
            "days_since_last_ban": p.get("DaysSinceLastBan", 0),
            "community_banned": p.get("CommunityBanned", False),
            "number_of_game_bans": p.get("NumberOfGameBans", 0),
            "economy_ban": p.get("EconomyBan", "none"),
        }


api = API()


# ============================================================
# LLM7 КЛИЕНТ (единственный ИИ)
# ============================================================
class LLM7Client:
    def __init__(self, base_url: str = LLM7_BASE_URL,
                 api_key: str = LLM7_API_KEY,
                 model: str = LLM7_MODEL,
                 timeout: int = 25):
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
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

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

        payload = {
            "model": use_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
                            await log_error(bot, "LLM7", "rate-limit (429)")
                            return None
                        if r.status != 200:
                            body = await r.text()
                            await log_error(bot, "LLM7", f"статус {r.status}: {body[:200]}")
                            return None

                        data = await r.json(content_type=None)
                        try:
                            return data["choices"][0]["message"]["content"]
                        except (KeyError, IndexError, TypeError):
                            await log_error(bot, "LLM7", f"неожиданный ответ: {str(data)[:200]}")
                            return None
                except asyncio.TimeoutError:
                    print(f"⚠️ LLM7: таймаут {use_timeout} сек (попытка {attempt})")
                    if attempt == 2:
                        return None
                except Exception as e:
                    self._last_call = time.time()
                    await log_error(bot, "LLM7.chat", e)
                    return None
        return None


llm7 = LLM7Client()


async def ai_chat_with_fallback(prompt, system=None, history=None,
                                model="fast", max_tokens=500,
                                temperature=0.6, timeout=25) -> tuple[str | None, str]:
    """Отправляет запрос в LLM7.io. Возвращает (ответ, источник 'llm7'|'none')."""
    answer = await llm7.chat(
        prompt=prompt, system=system, history=history,
        model=model, max_tokens=max_tokens,
        temperature=temperature, timeout=timeout,
    )
    if answer:
        return answer, "llm7"
    return None, "none"


# ============================================================
# ПАМЯТЬ ДИАЛОГА /ai + КУЛДАУН
# ============================================================
ai_chat_history: dict[int, deque] = defaultdict(
    lambda: deque(maxlen=AI_CHAT_HISTORY_SIZE)
)
ai_chat_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
ai_last_call_by_user: dict[int, float] = {}


# ============================================================
# УЛУЧШЕНИЕ №3 — СТАТИСТИКА /ai
# ============================================================
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
        d["last_channel"] = str(channel_id)
        users = d.setdefault("users", {})
        users[str(user_id)] = int(users.get(str(user_id), 0)) + 1
        d["users"] = dict(sorted(users.items(), key=lambda kv: kv[1], reverse=True)[:20])
    await ai_stats_store.update(_upd)


# ============================================================
# ПАРСИНГ HTML CS2RED
# ============================================================
async def check_punishment_via_html(steam_id: str, kind: str) -> bool:
    category = "MUTES" if kind == "mutes" else "BANS"
    url = f"https://cs2red.ru/bans?category={category}"

    html = await api._get_html(url)
    if not html:
        await log_error(bot, f"punishment[{kind}]", f"HTML с {url} не получен")
        return False

    soup = BeautifulSoup(html, "html.parser")
    profile_link = soup.find("a", href=f"/profile/{steam_id}")
    if not profile_link:
        print(f"🔍 [{kind}] SteamID {steam_id} не найден на первой странице")
        return False

    row = profile_link
    for _ in range(10):
        row = row.parent
        if row is None:
            break
        classes = row.get("class") or []
        if "self-stretch" in classes and "h-16" in classes:
            break
    if row is None:
        print(f"🔍 [{kind}] Не удалось найти строку для {steam_id}")
        return False

    row_text = row.get_text(" ", strip=True)
    if "Размучен" in row_text or "Разбанен" in row_text or "Снят" in row_text:
        print(f"🔍 [{kind}] {steam_id} - снят")
        return False

    print(f"🔍 [{kind}] {steam_id} - АКТИВЕН")
    return True


# ============================================================
# ДОСТУП / МОДЕРАТОРЫ
# ============================================================
def is_moderator(user_id: int, guild: discord.Guild) -> bool:
    if user_id in moders_store.read():
        return True
    member = guild.get_member(user_id)
    return bool(member and member.guild_permissions.administrator)


def get_all_reviewer_role_ids() -> list:
    return [ALLOWED_ROLE_ID, REVIEWER_ROLE_ID_2, SPAM_VOTE_ROLE_ID,
            EXTRA_REVIEWER_ROLE_1, EXTRA_REVIEWER_ROLE_2, EXTRA_REVIEWER_ROLE_3]


def _has_any_role(member: discord.Member, role_ids) -> bool:
    ids = {r.id for r in member.roles}
    return any(rid and rid in ids for rid in role_ids)


def user_can_review(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_any_role(
        member, get_all_reviewer_role_ids())


def user_can_spam_vote(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_any_role(
        member, [SPAM_VOTE_ROLE_ID])


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


# ============================================================
# ЗАПРЕТЫ НА ЗАЯВКИ
# ============================================================
def is_user_blocked(discord_id: int) -> tuple:
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
        until_str = entry.get("until")
        try:
            until = datetime.datetime.fromisoformat(until_str)
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


# ============================================================
# ХЕЛПЕРЫ
# ============================================================
def _fmt_timestamp(ts):
    if not ts:
        return "-"
    if ts == 0:
        return "перманентно"
    try:
        return datetime.datetime.fromtimestamp(ts, UTC).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)


def _admin_name(entry):
    u = entry.get("user")
    if u and u.get("nick"):
        return u["nick"]
    admin_id = entry.get("adminId")
    if admin_id == 0:
        return "Система (автобан)"
    return f"ID {admin_id}" if admin_id else "-"


def build_activity_bar(hours: float, goal: float = 8.0, length: int = 10) -> str:
    ratio = max(0.0, min(1.0, hours / goal)) if goal > 0 else 0.0
    filled = int(round(ratio * length))
    if hours <= 0:
        emoji, status = "⚫", "Не играет"
    elif hours < goal * 0.25:
        emoji, status = "🔴", "Очень мало"
    elif hours < goal * 0.5:
        emoji, status = "🟠", "Мало"
    elif hours < goal * 0.75:
        emoji, status = "🟡", "Средне"
    elif hours < goal:
        emoji, status = "🟢", "Хорошо"
    elif hours == goal:
        emoji, status = "🟢", "Выполнено"
    else:
        emoji, status = "🟢", "Отлично"
    extra = f" (+{hours - goal:.1f} ч.)" if hours > goal else ""
    return f"`{'█' * filled}{'░' * (length - filled)}` {hours:.1f} / {goal:.0f} ч. - {emoji} {status}{extra}"


def get_player_activity(steam_id: str) -> float:
    entry = players_store.read().get(steam_id, {})
    activity = entry.get("activity", {})
    if not isinstance(activity, dict):
        return 0.0
    total = 0.0
    for hours in activity.values():
        try:
            total += float(hours)
        except (ValueError, TypeError):
            continue
    return total


def extract_discord_id_from_embed(embed: discord.Embed) -> int:
    for field in embed.fields:
        if field.name == "Discord (упоминание)":
            m = re.search(r"\d{17,20}", field.value)
            if m:
                return int(m.group(0))
    return 0


# ============================================================
# СБОР ПРОФИЛЯ
# ============================================================
async def build_player_profile(guild: discord.Guild, discord_id: int,
                               steam_id: str = None) -> dict:
    profile = {
        "discord_id": str(discord_id),
        "updated_at": now_utc().isoformat(),
    }
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

    summary = await api.steam_summary(steam_id)
    if summary:
        profile["steam_avatar"] = summary.get("avatarfull")
        profile["steam_status"] = {0: "offline", 1: "online", 2: "busy", 3: "away"}.get(
            summary.get("personastate"), "unknown")
        profile["steam_nick"] = summary.get("personaname")
    sb = await api.steam_bans(steam_id)
    if sb:
        profile["steam_bans"] = sb
    return profile


# ============================================================
# ОТПРАВКА ПРОФИЛЯ
# ============================================================
async def send_player_report(bot: commands.Bot, profile: dict):
    channel = bot.get_channel(DB_CHANNEL_ID)
    if not channel:
        await log_error(bot, "send_player_report", f"Канал {DB_CHANNEL_ID} не найден")
        return
    embed = discord.Embed(title="👤 Профиль игрока", color=0x2B2D31,
                          timestamp=now_utc())

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
        vac_lines = ["❌ **VAC-бан**: "
                     f"{sb.get('number_of_vac_bans', 0)} шт. ({sb.get('days_since_last_ban', 0)} дн. назад)"
                     if sb.get("vac_banned") else "✅ VAC-банов нет"]
        if sb.get("community_banned"):
            vac_lines.append("❌ **Бан сообщества Steam**")
        if sb.get("number_of_game_bans", 0) > 0:
            vac_lines.append(f"❌ **Игровых банов**: {sb['number_of_game_bans']}")
        if sb.get("economy_ban") and sb["economy_ban"] != "none":
            vac_lines.append(f"❌ **Economy ban**: {sb['economy_ban']}")
        field("🛡️ Steam-баны", "\n".join(vac_lines))

    history = []
    if sb.get("vac_banned"):
        history.append("❌ VAC-бан")
    hours = profile.get("activity_hours", 0.0)
    if hours < ACTIVITY_MIN_HOURS:
        history.append(f"⚠️ Малоактивный ({hours:.1f} ч. < {ACTIVITY_MIN_HOURS})")
    field("Итоговый статус", "\n".join(history) or "✅ Чист")

    admins = profile.get("cs2red_admins") or []
    if admins:
        lines = []
        for a in admins[:10]:
            sid = a.get("serverId", 0)
            srv = "все серверы" if sid == 0 else f"сервер {sid}"
            exp = a.get("expires", 0)
            lines.append(f"👑 roleId={a.get('roleId', '-')} на {srv}, "
                         f"до: {'перманентно' if exp == 0 else _fmt_timestamp(exp)}")
        if len(admins) > 10:
            lines.append(f"...и ещё {len(admins) - 10}")
        field(f"👑 Админ-права ({len(admins)})", "\n".join(lines))

    vips = [v for v in (profile.get("cs2red_vips") or [])
            if v.get("expires", 0) == 0 or v.get("expires", 0) >= int(now_utc().timestamp())]
    if vips:
        lines = [f"⭐ {v.get('group', '-')} до "
                 f"{'перманентно' if v.get('expires', 0) == 0 else _fmt_timestamp(v.get('expires'))}"
                 for v in vips[:10]]
        field(f"⭐ Активные VIP ({len(vips)})", "\n".join(lines))

    if profile.get("steam_avatar"):
        embed.set_thumbnail(url=profile["steam_avatar"])
    embed.set_footer(text=f"Обновлено: {profile.get('updated_at', '-')}")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        await log_error(bot, "send_player_report.send", e)


# ============================================================
# ЛОГИ
# ============================================================
async def _send(bot: commands.Bot, channel_id: int, text: str):
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            await channel.send(text[:1900] + ("\n...(обрезано)" if len(text) > 1900 else ""))
        except Exception as e:
            print(f"⚠️ Лог: {e}")


async def log_to_channel(bot: commands.Bot, text: str):
    if LOG_CHANNEL_ID:
        await _send(bot, LOG_CHANNEL_ID, text)


async def log_to_applications(bot: commands.Bot, text: str):
    if APPLICATION_LOGS_CHANNEL_ID:
        await _send(bot, APPLICATION_LOGS_CHANNEL_ID, text)


def utc_stamp() -> str:
    return now_utc().strftime("%d.%m.%Y %H:%M")


# ============================================================
# СИНХРОНИЗАЦИЯ РОЛЕЙ
# ============================================================
async def sync_role_by_id(guild: discord.Guild, member: discord.Member,
                          steam_id: str) -> str:
    user = await api.cs2red_user(steam_id)
    if user is None:
        return f"❌ {member.display_name}: игрок не найден"
    target_name = ROLE_MAP.get(user.get("roleId"))
    managed = {n for n in ROLE_MAP.values() if n}
    current = {r for r in member.roles if r.name in managed}

    if target_name is None:
        if current:
            for r in current:
                await member.remove_roles(r)
            return f"🔄 {member.display_name}: сняты роли"
        return f"ℹ️ {member.display_name}: изменений нет"

    target = discord.utils.get(guild.roles, name=target_name)
    if target is None:
        return f"⚠️ {member.display_name}: роль '{target_name}' не найдена"
    if current == {target}:
        return f"✅ {member.display_name}: уже имеет '{target_name}'"
    for r in current:
        if r != target:
            await member.remove_roles(r)
    try:
        await member.add_roles(target)
        return (f"✅ {member.display_name}: выдана '{target_name}' "
                f"(nick={user.get('nick', '-')}, roleId={user.get('roleId')})")
    except discord.Forbidden:
        return f"❌ {member.display_name}: нет прав"


async def sync_clan_role_by_id(guild: discord.Guild, member: discord.Member,
                               steam_id: str) -> str:
    if not CLAN_ROLE_MAP:
        return f"ℹ️ {member.display_name}: CLAN_ROLE_MAP пуст"
    clan = await api.player_clan(steam_id)
    managed_ids = set(CLAN_ROLE_MAP.values())
    held = [r for r in member.roles if r.id in managed_ids]

    if clan is None:
        for r in held:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass
        return (f"🔄 {member.display_name}: клан снят (нет клана)" if held
                else f"ℹ️ {member.display_name}: без клана")

    target_id = CLAN_ROLE_MAP.get(clan["clan_id"])
    if target_id is None:
        for r in held:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass
        return f"ℹ️ {member.display_name}: клан без привязки роли ({clan['clan_name']})"

    target = guild.get_role(target_id)
    if target is None:
        return f"⚠️ {member.display_name}: Discord-роль {target_id} не найдена"
    for r in held:
        if r.id != target_id:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass
    if target in member.roles:
        return f"✅ {member.display_name}: уже в клане '{clan['clan_name']}' ({clan['clan_tag']})"
    try:
        await member.add_roles(target)
        return f"✅ {member.display_name}: выдан клан '{clan['clan_name']}' ({clan['clan_tag']})"
    except discord.Forbidden:
        return f"❌ {member.display_name}: нет прав"


# ============================================================
# БАНЫ / МУТЫ - РОЛИ
# ============================================================
PUNISHMENTS = {
    "ban": {"endpoint": "bans", "role_id": BANNED_ROLE_ID, "emoji": "🔨", "word": "Бан"},
    "mute": {"endpoint": "mutes", "role_id": MUTED_ROLE_ID, "emoji": "🔇", "word": "Мут"},
}


async def check_punishment_roles(bot: commands.Bot, guild: discord.Guild,
                                 kind: str) -> list:
    cfg = PUNISHMENTS[kind]
    role = guild.get_role(cfg["role_id"])
    if role is None:
        return [f"❌ Роль {cfg['role_id']} не найдена"]
    links = links_store.read()
    print(f"{cfg['emoji']} Проверка {kind} для {len(links)} игроков...")
    actions = []
    for discord_id, steam_id in list(links.items()):
        member = guild.get_member(int(discord_id))
        if member is None:
            continue
        punished = await check_punishment_via_html(steam_id, cfg["endpoint"])
        has_role = role in member.roles
        if punished == has_role:
            continue
        try:
            if punished:
                await member.add_roles(role, reason=f"{cfg['word']} cs2red.ru")
                actions.append(f"{cfg['emoji']} Выдана роль «{role.name}»: {member.display_name}")
            else:
                await member.remove_roles(role, reason=f"Снятие {cfg['word']} cs2red.ru")
                actions.append(f"✅ Снята роль «{role.name}»: {member.display_name}")
            await log_to_applications(
                bot,
                f"{cfg['emoji']} **{cfg['word']} {'выдан' if punished else 'снят'}**\n"
                f"👤 Игрок: {member.mention}\n🎭 Роль: {role.mention}\n🕒 {utc_stamp()} (UTC)")
        except discord.Forbidden:
            actions.append(f"❌ Нет прав для {member.display_name}")
        except Exception as e:
            await log_error(bot, f"check_punishment_roles:{kind}", e)
        await asyncio.sleep(REQUEST_DELAY)
    return actions


# ============================================================
# ВЕТКИ ЗАЯВОК
# ============================================================
async def close_application_thread(thread: discord.Thread,
                                   closed_by: discord.Member, reason: str):
    if not isinstance(thread, discord.Thread):
        return
    try:
        try:
            await thread.send(f"🔒 **Ветка закрыта.**\n**Решение:** {reason}\n"
                              f"**Закрыл:** {closed_by.mention}")
        except Exception:
            pass
        await asyncio.sleep(5)
        try:
            await thread.edit(archived=True, locked=True,
                              reason=f"Заявка {reason} ({closed_by})")
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
        print(f"✅ Ветка {thread.name} закрыта ({reason})")
    except Exception as e:
        await log_error(bot, "close_application_thread", e)


# ============================================================
# ГОЛОСА
# ============================================================
def _get_votes(message_id: int) -> dict:
    return votes_store.read().get(str(message_id)) or {"accept": 0, "deny": 0, "voters": []}


async def _save_votes(message_id: int, state: dict):
    await votes_store.update(lambda d: d.update({str(message_id): state}))


async def _vote(interaction: discord.Interaction, kind: str):
    await interaction.response.defer()
    if not user_can_review(interaction.user):
        await interaction.followup.send("❌ Нет прав.", ephemeral=True)
        return
    state = _get_votes(interaction.message.id)
    if interaction.user.id in state["voters"] and not user_can_spam_vote(interaction.user):
        await interaction.followup.send("Вы уже голосовали.", ephemeral=True)
        return
    state[kind] += 1
    if interaction.user.id not in state["voters"]:
        state["voters"].append(interaction.user.id)
    await _save_votes(interaction.message.id, state)

    view = ApplicationManagement()
    view.update_labels(interaction.message.id)
    if state[kind] >= VOTES_REQUIRED:
        embed = interaction.message.embeds[0]
        status = "Принят" if kind == "accept" else "Отклонен"
        embed.set_footer(text=f"Quantum • Статус: {status}")
        for child in view.children:
            child.disabled = True
        try:
            await interaction.message.edit(embed=embed, view=view)
        except Exception:
            pass
        target_id = extract_discord_id_from_embed(embed)
        member = interaction.guild.get_member(target_id) if target_id else None
        if kind == "accept" and member and AUTO_ROLE_ID:
            role_to_give = interaction.guild.get_role(AUTO_ROLE_ID)
            if role_to_give:
                try:
                    await member.add_roles(role_to_give)
                    await log_to_channel(
                        interaction.client,
                        f"✅ Заявка принята. {member.mention} получил {role_to_give.mention}")
                    await log_to_applications(
                        interaction.client,
                        f"✅ **Заявка принята**\n👤 Игрок: {member.mention}\n"
                        f"🎖 Роль: {role_to_give.mention}\n👮 Принял: {interaction.user.mention}\n"
                        f"🕒 {utc_stamp()} (UTC)")
                except discord.Forbidden:
                    pass
        if member:
            await log_to_channel(interaction.client,
                                 f"{'✅' if kind == 'accept' else '❌'} Заявка "
                                 f"{'принята' if kind == 'accept' else 'отклонена'}: {member.mention}")
            await log_to_applications(
                interaction.client,
                f"{'✅' if kind == 'accept' else '❌'} **Заявка "
                f"{'принята' if kind == 'accept' else 'отклонена'}**\n👤 Игрок: {member.mention}\n"
                f"👮 {'Принял' if kind == 'accept' else 'Отклонил'}: {interaction.user.mention}\n"
                f"🕒 {utc_stamp()} (UTC)")
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

    def update_labels(self, message_id: int):
        state = _get_votes(message_id)
        for child in self.children:
            if child.custom_id == "accept_btn":
                child.label = f"Принять {state['accept']}/{VOTES_REQUIRED}"
            elif child.custom_id == "deny_btn":
                child.label = f"Отклонить {state['deny']}/{VOTES_REQUIRED}"
            elif child.custom_id == "voted_list_btn":
                child.label = f"👥 {len(state['voters'])}"

    @discord.ui.button(label="🙋 Взять", style=discord.ButtonStyle.primary,
                       custom_id="take_btn", row=0)
    async def take(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not user_can_review(interaction.user):
            await interaction.followup.send("❌ Нет прав.", ephemeral=True)
            return
        await interaction.followup.send(
            f"🙋 Заявку **взял в работу** {interaction.user.mention}.")
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        if isinstance(interaction.channel, discord.Thread):
            try:
                embed = interaction.message.embeds[0]
                allowed = {extract_discord_id_from_embed(embed), interaction.user.id}
                if interaction.guild.me:
                    allowed.add(interaction.guild.me.id)
                members = await interaction.channel.fetch_members()
                for m in members:
                    if m.id not in allowed:
                        try:
                            await interaction.channel.remove_user(m)
                        except Exception:
                            pass
                await interaction.channel.send(
                    f"🙋 Ветку взял {interaction.user.mention}. Остальные участники удалены.")
            except Exception as e:
                print(f"⚠️ take-очистка ветки: {e}")

    @discord.ui.button(label="Принять 0/2", style=discord.ButtonStyle.success,
                       custom_id="accept_btn", row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _vote(interaction, "accept")

    @discord.ui.button(label="Отклонить 0/2", style=discord.ButtonStyle.danger,
                       custom_id="deny_btn", row=0)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _vote(interaction, "deny")

    @discord.ui.button(label="🚫 Выдать запрет", style=discord.ButtonStyle.secondary,
                       custom_id="tempban_btn", row=1)
    async def temp_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not user_can_review(interaction.user):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        target_id = extract_discord_id_from_embed(interaction.message.embeds[0])
        if not target_id:
            await interaction.response.send_message("❌ Discord ID не найден.", ephemeral=True)
            return
        await interaction.response.send_modal(TempBanModal(target_id))

    @discord.ui.button(label="⛔ Перм. запрет", style=discord.ButtonStyle.danger,
                       custom_id="permban_btn", row=1)
    async def perm_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not user_can_review(interaction.user):
            await interaction.followup.send("❌ Нет прав.", ephemeral=True)
            return
        target_id = extract_discord_id_from_embed(interaction.message.embeds[0])
        if not target_id:
            await interaction.followup.send("❌ Discord ID не найден.", ephemeral=True)
            return

        async def _set(d):
            d[str(target_id)] = {"type": "perm", "until": None,
                                 "reason": f"Выдал {interaction.user}"}
        await bans_store.update(_set)
        await interaction.followup.send(
            f"⛔ Пользователю <@{target_id}> выдан **перманентный запрет**.")
        await log_to_channel(interaction.client,
                             f"⛔ **Перманентный запрет**\n**Кому:** <@{target_id}>\n"
                             f"**Выдал:** {interaction.user.mention}")
        await log_to_applications(
            interaction.client,
            f"⛔ **Перманентный запрет**\n👤 Игрок: <@{target_id}>\n"
            f"👮 Выдал: {interaction.user.mention}\n🕒 {utc_stamp()} (UTC)")

    @discord.ui.button(label="✅ Снять запрет", style=discord.ButtonStyle.success,
                       custom_id="unban_btn", row=1)
    async def unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not user_can_review(interaction.user):
            await interaction.followup.send("❌ Нет прав.", ephemeral=True)
            return
        target_id = extract_discord_id_from_embed(interaction.message.embeds[0])
        if not target_id:
            await interaction.followup.send("❌ Discord ID не найден.", ephemeral=True)
            return
        removed = await bans_store.update(lambda d: d.pop(str(target_id), None))
        if removed is not None:
            await interaction.followup.send(f"✅ С пользователя <@{target_id}> **снят запрет**.")
            await log_to_channel(interaction.client,
                                 f"✅ **Запрет снят**\n**С кого:** <@{target_id}>\n"
                                 f"**Снял:** {interaction.user.mention}")
            await log_to_applications(
                interaction.client,
                f"✅ **Запрет снят**\n👤 Игрок: <@{target_id}>\n👮 Снял: {interaction.user.mention}\n"
                f"🕒 {utc_stamp()} (UTC)")
        else:
            await interaction.followup.send("ℹ️ Нет активных запретов.", ephemeral=True)

    @discord.ui.button(label="👥 0", style=discord.ButtonStyle.secondary,
                       custom_id="voted_list_btn", row=1)
    async def voted_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = _get_votes(interaction.message.id)
        if not state["voters"]:
            await interaction.response.send_message("Никто не голосовал.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Голосовали: " + ", ".join(f"<@{uid}>" for uid in state["voters"]),
            ephemeral=True)


class TempBanModal(discord.ui.Modal, title="Выдать запрет на заявки"):
    def __init__(self, target_id: int):
        super().__init__()
        self.target_id = target_id
        self.hours = discord.ui.TextInput(
            label="На сколько часов выдать запрет?",
            placeholder="Например: 1, 12, 24, 168, 720", default="12", max_length=6)
        self.reason = discord.ui.TextInput(
            label="Причина (необязательно)",
            placeholder="Например: нарушение правил клана",
            required=False, max_length=200)
        self.add_item(self.hours)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hours = int(self.hours.value.strip())
            if hours <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Неверное число часов.", ephemeral=True)
            return
        until = (now_utc() + datetime.timedelta(hours=hours)).isoformat()

        async def _set(d):
            d[str(self.target_id)] = {"type": "temp", "until": until,
                                      "reason": self.reason.value.strip() or "-"}
        await bans_store.update(_set)

        days, rem = divmod(hours, 24)
        duration_text = (f"{days} д. {rem} ч." if days and rem else
                         f"{days} д." if days else f"{hours} ч.")
        until_display = until.replace("T", " ")[:16]
        await interaction.response.send_message(
            f"🚫 Пользователю <@{self.target_id}> выдан **запрет**.\n"
            f"**Срок:** {duration_text}\n**Снимется:** `{until_display}` (UTC)\n"
            f"**Причина:** {self.reason.value or '-'}\n**Выдал:** {interaction.user.mention}")
        await log_to_channel(interaction.client,
                             f"🚫 **Запрет на заявки**\n**Кому:** <@{self.target_id}>\n"
                             f"**Срок:** {duration_text}\n**Причина:** {self.reason.value or '-'}\n"
                             f"**Выдал:** {interaction.user.mention}")
        await log_to_applications(
            interaction.client,
            f"🚫 **Временный запрет**\n👤 Игрок: <@{self.target_id}>\n⏱ Срок: **{duration_text}**\n"
            f"📅 Снимется: `{until_display}` (UTC)\n📝 Причина: {self.reason.value or '-'}\n"
            f"👮 Выдал: {interaction.user.mention}\n🕒 {utc_stamp()} (UTC)")


# ============================================================
# МОДАЛЬНОЕ ОКНО ЗАЯВКИ
# ============================================================
class QuestionnaireModal(discord.ui.Modal, title="Заявка в клан"):
    def __init__(self, clan_name):
        super().__init__()
        self.clan_name = clan_name
        self.nickname = discord.ui.TextInput(label="Ваш игровой никнейм",
                                             placeholder="Введите ваш игровой никнейм")
        self.steam_input = discord.ui.TextInput(
            label="Steam-профиль (ссылка или SteamID64)",
            placeholder="https://steamcommunity.com/profiles/7656119... или 7656119...")
        self.age = discord.ui.TextInput(label="Ваш возраст", placeholder="Например: 16")
        self.time = discord.ui.TextInput(
            label="Время, когда удобно играть (по МСК)",
            placeholder="Например: с 18:00 до 22:00")
        self.reason = discord.ui.TextInput(
            label="Комментарий (не обязательно)", style=discord.TextStyle.paragraph,
            placeholder="Почему хотите вступить?", required=False)
        for item in (self.nickname, self.steam_input, self.age, self.time, self.reason):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        blocked, reason_text = is_user_blocked(interaction.user.id)
        if blocked:
            await interaction.followup.send(reason_text, ephemeral=True)
            return

        m = re.search(r"\d{17}", self.steam_input.value.strip())
        steam_id = m.group(0) if m else None
        if steam_id:
            steam_url = f"https://steamcommunity.com/profiles/{steam_id}"
            cs2red_url = f"https://cs2red.ru/profile/{steam_id}"
            csstats_url = f"https://csstats.gg/player/{steam_id}"
            steam_id_display = f"`{steam_id}`"
        else:
            steam_url, cs2red_url, csstats_url = ("https://steamcommunity.com",
                                                  "https://cs2red.ru", "https://csstats.gg")
            steam_id_display = "`- не распознан -`"

        embed_staff = discord.Embed(title="ЗАЯВКА В КЛАН", color=APPLY_EMBED_COLOR)
        embed_staff.add_field(name="Игрок", value=self.nickname.value, inline=False)
        embed_staff.add_field(name="Профиль Steam", value=f"[перейти]({steam_url})", inline=False)
        embed_staff.add_field(name="Профиль на сайте", value=f"[перейти]({cs2red_url})", inline=False)
        embed_staff.add_field(name="Статистика csstats.gg", value=f"[перейти]({csstats_url})", inline=False)
        embed_staff.add_field(name="Возраст", value=f"```\n{self.age.value}\n```", inline=False)
        embed_staff.add_field(name="Discord для связи", value=f"```\n{interaction.user.name}\n```",
                              inline=False)
        embed_staff.add_field(name="Время в которое удобно играть (по МСК)",
                              value=f"```\n{self.time.value}\n```", inline=False)
        if self.reason.value and self.reason.value.strip():
            embed_staff.add_field(name="Комментарий", value=f"```\n{self.reason.value}\n```",
                                  inline=False)
        embed_staff.add_field(name="SteamID", value=steam_id_display, inline=False)
        embed_staff.add_field(name="Discord (упоминание)", value=interaction.user.mention,
                              inline=False)
        embed_staff.set_thumbnail(url=interaction.user.display_avatar.url)
        embed_staff.set_footer(text=f"{CLAN_NAME} • {utc_stamp()}")

        apps_channel = interaction.guild.get_channel(APPLICATIONS_CHANNEL_ID)
        if apps_channel:
            try:
                view = ApplicationManagement()
                msg = await apps_channel.send(
                    content=f"🔔 Новая заявка от {interaction.user.mention}",
                    embed=embed_staff, view=view)
                view.update_labels(msg.id)
                await msg.edit(view=view)
                await log_to_applications(
                    interaction.client,
                    f"🔔 **Новая заявка**\n👤 Игрок: {interaction.user.mention}\n"
                    f"🎮 Ник: {self.nickname.value}\n🕒 {utc_stamp()} (UTC)")
            except Exception as e:
                await log_error(bot, "questionnaire.send", e)

        await interaction.followup.send("✅ Ваша заявка отправлена на рассмотрение!",
                                        ephemeral=True)
        asyncio.create_task(_create_application_thread(interaction, embed_staff))


async def _create_application_thread(interaction: discord.Interaction, embed: discord.Embed):
    try:
        threads_channel = interaction.guild.get_channel(THREADS_CHANNEL_ID)
        if threads_channel is None:
            return
        thread = await threads_channel.create_thread(
            name=f"заявка-{interaction.user.name.lower()}"[:100],
            type=discord.ChannelType.private_thread,
            invitable=False, auto_archive_duration=1440,
            reason=f"Заявка от {interaction.user}")
        try:
            await thread.add_user(interaction.user)
        except Exception:
            pass
        added, tasks_ = set(), []
        for rid in get_all_reviewer_role_ids():
            role = interaction.guild.get_role(rid) if rid else None
            if role:
                for m in role.members:
                    if m.id not in added and not m.bot:
                        added.add(m.id)
                        tasks_.append(thread.add_user(m))
        for i in range(0, len(tasks_), 20):
            await asyncio.gather(*tasks_[i:i + 20], return_exceptions=True)
        try:
            view = ApplicationManagement()
            msg = await thread.send(content=f"{interaction.user.mention}, ваша заявка на рассмотрении.",
                                    embed=embed, view=view)
            view.update_labels(msg.id)
            await msg.edit(view=view)
        except Exception as e:
            await log_error(bot, "_create_application_thread.send", e)
    except Exception as e:
        await log_error(bot, "_create_application_thread", e)


class ClanSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Выберите клан для подачи заявки",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=CLAN_NAME,
                                          description=f"Основной состав клана {CLAN_NAME}")])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(QuestionnaireModal(self.values[0]))


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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command = getattr(interaction, "command", None)
        if command is None or command.name in PUBLIC_COMMANDS:
            return True
        allowed = is_moderator(interaction.user.id, interaction.guild)
        if not allowed and not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ У вас нет доступа к этой команде.", ephemeral=True)
        return allowed

    async def setup_hook(self):
        await api.start()
        await llm7.start()
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"✅ Синхронизировано команд: {len(synced)}")
        self.add_view(ApplicationManagement())
        auto_sync.start()
        ban_check.start()
        mute_check.start()
        activity_tracker.start()
        ai_script_analysis.start()

    async def close(self):
        await api.close()
        await llm7.close()
        await super().close()


bot = MyBot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction,
                               error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CheckFailure):
        msg = "❌ У вас нет доступа к этой команде."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass
        return
    await log_error(interaction.client, f"cmd:{interaction.command}", error)


@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} готов!")
    print(f"🔑 LLM7_API_KEY: {'ЗАДАН' if LLM7_API_KEY and LLM7_API_KEY != 'unused' else 'unused'}")
    asyncio.create_task(_warmup_llm7())


async def _warmup_llm7():
    await asyncio.sleep(5)
    print("🔥 Прогрев LLM7...")
    for model in ("fast", "default"):
        try:
            r = await llm7.chat("ping", system="Ответь одним словом: pong",
                                model=model, max_tokens=10, timeout=40)
            print(f"🔥 LLM7 [{model}] прогрет: {'OK' if r else 'FAIL'}")
            if r:
                break
        except Exception as e:
            print(f"⚠️ Прогрев LLM7 [{model}]: {e}")


def admin_only(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


async def _admin_guard(interaction: discord.Interaction) -> bool:
    if not admin_only(interaction):
        await interaction.response.send_message("❌ Нужны права администратора.",
                                                ephemeral=True)
        return False
    return True


# ============================================================
# КОМАНДЫ ПРИВЯЗКИ
# ============================================================
@bot.tree.command(name="link", description="Привязать свой Discord к SteamID")
@app_commands.describe(steam_id="Твой SteamID64 (17 цифр)")
@app_commands.checks.cooldown(1, 30)
async def link(interaction: discord.Interaction, steam_id: str):
    if not (steam_id.isdigit() and len(steam_id) == 17 and steam_id.startswith("7656119")):
        await interaction.response.send_message("❌ Неверный SteamID.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    existing = links_store.read()
    owner = next((did for did, sid in existing.items() if sid == steam_id), None)
    if owner and int(owner) != interaction.user.id:
        await interaction.followup.send("❌ Этот SteamID уже привязан к другому аккаунту.",
                                        ephemeral=True)
        return

    user = await api.cs2red_user(steam_id)
    if user is None:
        await interaction.followup.send(f"❌ Игрок `{steam_id}` не найден.", ephemeral=True)
        return

    await links_store.update(lambda d: d.update({str(interaction.user.id): steam_id}))
    await interaction.followup.send(
        f"✅ Привязано! SteamID `{steam_id}` (ник: **{user.get('nick', '-')}**).",
        ephemeral=True)
    try:
        status = await sync_role_by_id(interaction.guild, interaction.user, steam_id)
        clan_status = await sync_clan_role_by_id(interaction.guild, interaction.user, steam_id)
        await log_to_channel(interaction.client, f"🔗 /link - {status}\n{clan_status}")
    except Exception as e:
        await log_error(interaction.client, "/link", e)


@bot.tree.command(name="unlink", description="Отвязать свой Discord от SteamID")
async def unlink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    removed_sid = await links_store.update(
        lambda d: d.pop(str(interaction.user.id), None))
    if removed_sid is None:
        await interaction.followup.send("ℹ️ Ты не был привязан.", ephemeral=True)
        return
    managed_names = {n for n in ROLE_MAP.values() if n}
    managed_ids = set(CLAN_ROLE_MAP.values())
    removed = []
    for role in interaction.user.roles:
        if role.name in managed_names or role.id in managed_ids:
            try:
                await interaction.user.remove_roles(role)
                removed.append(role.name)
            except discord.Forbidden:
                pass
    await interaction.followup.send(
        f"✅ Отвязано. Сняты роли: {', '.join(removed) if removed else 'нет'}",
        ephemeral=True)


@bot.tree.command(name="sync_all", description="Синхронизировать всех привязанных")
async def sync_all(interaction: discord.Interaction):
    if not await _admin_guard(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    links = links_store.read()
    if not links:
        await interaction.followup.send("ℹ️ Нет привязанных.", ephemeral=True)
        return
    results = []
    for discord_id, steam_id in links.items():
        member = interaction.guild.get_member(int(discord_id))
        if member is None:
            results.append(f"⚠️ Discord ID {discord_id} не найден")
            continue
        results.append(await sync_role_by_id(interaction.guild, member, steam_id))
        results.append(await sync_clan_role_by_id(interaction.guild, member, steam_id))
        await asyncio.sleep(REQUEST_DELAY)
    text = f"📊 Синхронизировано: {len(results)}\n\n" + "\n".join(results)
    await interaction.followup.send(text[:1900], ephemeral=True)
    await log_to_channel(interaction.client, text)


# ============================================================
# АВТОДОПОЛНЕНИЕ + ПРОВЕРКА БАНОВ/МУТОВ
# ============================================================
async def linked_member_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    links = links_store.read()
    if not links:
        return []
    choices = []
    for discord_id, steam_id in links.items():
        member = interaction.guild.get_member(int(discord_id))
        if member is None:
            continue
        search = current.lower()
        if search and search not in member.display_name.lower() and search not in steam_id:
            continue
        choices.append(
            app_commands.Choice(name=f"{member.display_name} | {steam_id}",
                                value=str(member.id)))
        if len(choices) >= 25:
            break
    return choices


async def _check_single_punishment(interaction: discord.Interaction,
                                   member: discord.Member, kind: str) -> None:
    cfg = PUNISHMENTS[kind]
    role = interaction.guild.get_role(cfg["role_id"])
    if role is None:
        await interaction.followup.send(f"❌ Роль `{cfg['role_id']}` не найдена.",
                                        ephemeral=True)
        return

    steam_id = links_store.read().get(str(member.id))
    if not steam_id:
        await interaction.followup.send(
            f"❌ {member.mention} не привязан к SteamID. Сначала `/link`.", ephemeral=True)
        return

    html_kind = "bans" if kind == "ban" else "mutes"
    punished = await check_punishment_via_html(steam_id, html_kind)
    has_role = role in member.roles

    if punished == has_role:
        status = "уже имеет роль" if has_role else "чист (активных нет)"
        await interaction.followup.send(
            f"ℹ️ **{member.display_name}** - {status}. Изменений не требуется.",
            ephemeral=True)
        return

    try:
        if punished:
            await member.add_roles(role, reason=f"{cfg['word']} cs2red.ru")
            result = f"{cfg['emoji']} Выдана роль «{role.name}»: {member.mention}"
        else:
            await member.remove_roles(role, reason=f"Снятие {cfg['word']} cs2red.ru")
            result = f"✅ Снята роль «{role.name}»: {member.mention}"

        await interaction.followup.send(
            f"**{cfg['word']} - {member.display_name}**\n"
            f"SteamID: `{steam_id}`\n"
            f"Наказание активно: **{'да' if punished else 'нет'}**\n{result}",
            ephemeral=True)
        await log_to_applications(
            interaction.client,
            f"{cfg['emoji']} **{cfg['word']} {'выдан' if punished else 'снят'}**\n"
            f"👤 Игрок: {member.mention}\n"
            f"🎭 Роль: {role.mention}\n"
            f"🕒 {utc_stamp()} (UTC)\n"
            f"👮 Проверил: {interaction.user.mention}")
    except discord.Forbidden:
        await interaction.followup.send(
            f"❌ Нет прав для изменения ролей {member.mention}.", ephemeral=True)


@bot.tree.command(name="check_bans", description="Проверить активные баны игрока")
@app_commands.describe(member="Игрок (только привязанные)")
@app_commands.autocomplete(member=linked_member_autocomplete)
async def check_bans(interaction: discord.Interaction, member: str):
    if not await _admin_guard(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    try:
        member_id = int(member)
    except ValueError:
        await interaction.followup.send("❌ Некорректный игрок.", ephemeral=True)
        return
    target = interaction.guild.get_member(member_id)
    if target is None:
        await interaction.followup.send("❌ Пользователь не найден.", ephemeral=True)
        return
    await _check_single_punishment(interaction, target, "ban")


@bot.tree.command(name="check_mutes", description="Проверить активные муты игрока")
@app_commands.describe(member="Игрок (только привязанные)")
@app_commands.autocomplete(member=linked_member_autocomplete)
async def check_mutes(interaction: discord.Interaction, member: str):
    if not await _admin_guard(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    try:
        member_id = int(member)
    except ValueError:
        await interaction.followup.send("❌ Некорректный игрок.", ephemeral=True)
        return
    target = interaction.guild.get_member(member_id)
    if target is None:
        await interaction.followup.send("❌ Пользователь не найден.", ephemeral=True)
        return
    await _check_single_punishment(interaction, target, "mute")


@bot.tree.command(name="link_all", description="Массово привязать из mass_links.json")
async def link_all(interaction: discord.Interaction):
    if not await _admin_guard(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    mass_file = data_path("mass_links.json")
    if not mass_file.exists():
        await interaction.followup.send("❌ Файл `mass_links.json` не найден.", ephemeral=True)
        return
    try:
        with open(mass_file, "r", encoding="utf-8") as f:
            mass_data = json.load(f)
        if not isinstance(mass_data, dict):
            raise ValueError("файл должен быть JSON-объектом")
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка чтения: {e}", ephemeral=True)
        return

    added, errors = [], []
    for discord_id, steam_id in mass_data.items():
        steam_id = str(steam_id)
        member = interaction.guild.get_member(int(discord_id))
        if not (steam_id.isdigit() and len(steam_id) == 17):
            errors.append(f"⚠️ {discord_id}: неверный SteamID")
            continue
        if member is None:
            errors.append(f"⚠️ {discord_id}: нет на сервере")
            continue
        user = await api.cs2red_user(steam_id)
        if user is None:
            errors.append(f"⚠️ {member.display_name}: SteamID не найден")
            continue
        await links_store.update(lambda d: d.update({str(discord_id): steam_id}))
        added.append(f"✅ {member.display_name} -> {steam_id}")
        await asyncio.sleep(REQUEST_DELAY)

    text = (f"📊 **Массовая привязка**\n✅ Добавлено: {len(added)}\n❌ Ошибок: {len(errors)}\n\n")
    if added:
        text += "**Добавленные:**\n" + "\n".join(added[:20])
    if errors:
        text += "\n\n**Ошибки:**\n" + "\n".join(errors[:20])
    await interaction.followup.send(text[:1900], ephemeral=True)
    await log_to_channel(interaction.client, text)


@bot.tree.command(name="export_members", description="Выгрузить участников в mass_links.json")
async def export_members(interaction: discord.Interaction):
    if not await _admin_guard(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    members = {str(m.id): m.display_name for m in interaction.guild.members if not m.bot}
    bots_count = sum(1 for m in interaction.guild.members if m.bot)
    try:
        with open(data_path("mass_links.json"), "w", encoding="utf-8") as f:
            json.dump(members, f, ensure_ascii=False, indent=2)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)
        return
    await interaction.followup.send(
        f"✅ Выгружено: **{len(members)}** (ботов: {bots_count}).",
        ephemeral=True)
    await log_to_channel(interaction.client, f"📤 /export_members - {len(members)}.")


# ============================================================
# БАЗА ИГРОКОВ
# ============================================================
@bot.tree.command(name="player_info", description="Показать базу данных по игроку")
@app_commands.describe(member="Участник Discord")
async def player_info(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        profile = await build_player_profile(interaction.guild, member.id)
        if not profile.get("steamid64"):
            await interaction.followup.send("❌ У игрока нет SteamID.", ephemeral=True)
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
        await send_player_report(interaction.client, profile)
        await interaction.followup.send(f"✅ Профиль отправлен в <#{DB_CHANNEL_ID}>.",
                                        ephemeral=True)
    except Exception as e:
        await log_error(interaction.client, "/player_info", e)
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)


@bot.tree.command(name="player_note", description="Добавить заметку к профилю игрока")
@app_commands.describe(member="Участник Discord", note="Заметка")
async def player_note(interaction: discord.Interaction, member: discord.Member, note: str):
    if not await _admin_guard(interaction):
        return
    steam_id = links_store.read().get(str(member.id))
    if not steam_id:
        await interaction.response.send_message("❌ У игрока нет SteamID.", ephemeral=True)
        return

    async def _make_profile():
        return await build_player_profile(interaction.guild, member.id, steam_id)

    profile = players_store.read().get(steam_id) or await _make_profile()

    def _set(db):
        profile["notes"] = note
        profile["updated_at"] = now_utc().isoformat()
        db[steam_id] = profile
        return None
    await players_store.update(_set)
    await interaction.response.send_message(f"✅ Заметка добавлена для {member.mention}.",
                                            ephemeral=True)
    await send_player_report(interaction.client, profile)


@bot.tree.command(name="player_list", description="Показать базу игроков")
async def player_list(interaction: discord.Interaction):
    if not await _admin_guard(interaction):
        return
    db = players_store.read()
    if not db:
        await interaction.response.send_message("ℹ️ База пуста.", ephemeral=True)
        return
    links = links_store.read()
    rev = {sid: did for did, sid in links.items()}
    lines = []
    for sid, p in db.items():
        nick = p.get("cs2red_nick") or p.get("discord_name") or sid
        flags = []
        if p.get("steam_bans", {}).get("vac_banned"):
            flags.append("❌VAC")
        discord_id = p.get("discord_id") or rev.get(sid)
        if discord_id and interaction.guild.get_member(int(discord_id)):
            discord_part = f" - {interaction.guild.get_member(int(discord_id)).mention}"
        elif discord_id:
            discord_part = f" - `{discord_id}`"
        else:
            discord_part = f" - {p['discord_name']}" if p.get("discord_name") else ""
        nick_part = f"{nick} (Steam: {p['steam_nick']})" if p.get("steam_nick") else nick
        lines.append(f"{' '.join(flags)} `{sid}` - {nick_part}{discord_part}")
    text = "📊 **База игроков:**\n" + "\n".join(lines[:50])
    if len(lines) > 50:
        text += f"\n...и ещё {len(lines) - 50}"
    await interaction.response.send_message(text[:1900], ephemeral=True)


@bot.tree.command(name="lookup", description="Инфо о Discord-игроке")
@app_commands.describe(member="Участник Discord")
async def lookup(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    steam_id = links_store.read().get(str(member.id))
    if not steam_id:
        await interaction.followup.send(
            f"❌ {member.mention} не привязан. Сначала `/link`.", ephemeral=True)
        return
    user = await api.cs2red_user(steam_id)
    nick = user.get("nick", "-") if user else "-"
    role_id = user.get("roleId") if user else None
    clan = await api.player_clan(steam_id)
    clan_text = f" (клан: {clan['clan_name']})" if clan else " (без клана)"
    await interaction.followup.send(
        f"🎮 **{nick}**{clan_text}\n👤 Discord: {member.mention} (`{member.id}`)\n"
        f"SteamID64: `{steam_id}`\nРоль: **{role_display_name(role_id) if role_id else '-'}**",
        ephemeral=True)


# ============================================================
# /ping
# ============================================================
@bot.tree.command(name="ping", description="Проверить, жив ли бот")
async def ping(interaction: discord.Interaction):
    await interaction.response.defer(thinking=False)

    ws_latency_ms = bot.latency * 1000
    uptime_seconds = int(time.time() - BOT_START_TIME)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if uptime_seconds < 60:
        uptime_str = f"{uptime_seconds} сек."
    elif uptime_seconds < 3600:
        uptime_str = f"{minutes} мин. {seconds} сек."
    elif uptime_seconds < 86400:
        uptime_str = f"{hours} ч. {minutes} мин."
    else:
        uptime_str = f"{days} д. {hours} ч. {minutes} мин."

    status = ("🟢 Отличная связь" if ws_latency_ms < 150 else
              "🟡 Нормальная связь" if ws_latency_ms < 400 else
              "🟠 Высокая задержка")

    embed = discord.Embed(title="🏓 Pong!", color=0x2B2D31, timestamp=now_utc())
    embed.add_field(name="Статус", value="✅ Бот жив и работает", inline=False)
    embed.add_field(name="⏱ Аптайм", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="📡 WS-задержка", value=f"`{ws_latency_ms:.0f} мс`", inline=True)
    embed.add_field(name="Связь", value=status, inline=False)
    embed.add_field(name="Система",
                    value=f"Python {platform.python_version()} • discord.py {discord.__version__}",
                    inline=False)
    embed.set_footer(text=f"Quantum • {utc_stamp()} (UTC)")
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.followup.send(embed=embed)


# ============================================================
# /ai — ИИ в любом канале (с вариативностью и кулдауном)
# ============================================================
@bot.tree.command(name="ai", description="Спросить у ИИ (работает в любом канале)")
@app_commands.describe(
    prompt="Ваш вопрос или запрос",
    reset="Сбросить историю диалога в этом канале",
    long="Длинный ответ (медленнее, подробнее)",
)
async def ai(interaction: discord.Interaction, prompt: str,
             reset: bool = False, long: bool = False):
    await interaction.response.defer(thinking=True)

    # Улучшение №3 — кулдаун для одного пользователя
    last = ai_last_call_by_user.get(interaction.user.id, 0.0)
    if not long and time.time() - last < AI_CHAT_COOLDOWN_SEC:
        await interaction.followup.send(
            f"⏱ Подождите {AI_CHAT_COOLDOWN_SEC} сек. между запросами.", ephemeral=True)
        return
    ai_last_call_by_user[interaction.user.id] = time.time()

    channel_id = interaction.channel_id

    me = interaction.guild.me if interaction.guild else None
    if interaction.channel and me:
        perms = interaction.channel.permissions_for(me)
        if not perms.send_messages:
            await interaction.followup.send(
                "❌ У бота нет права писать в этом канале.", ephemeral=True)
            return

    if reset:
        ai_chat_history.pop(channel_id, None)

    history_snapshot = list(ai_chat_history.get(channel_id, []))

    if long:
        max_tokens = 1200
        timeout = 60
        model = "default"
    else:
        max_tokens = AI_CHAT_MAX_TOKENS
        timeout = AI_CHAT_TIMEOUT
        model = AI_CHAT_MODEL

    # Улучшение №2 — случайная фраза «Думаю…»
    thinking_msg = None
    try:
        thinking_msg = await interaction.followup.send(random.choice(AI_THINKING_PHRASES))
    except Exception:
        pass

    async with ai_chat_locks[channel_id]:
        # Улучшение №2 — случайный системный промпт
        answer, source = await ai_chat_with_fallback(
            prompt=prompt,
            system=random.choice(AI_CHAT_SYSTEM_PROMPTS),
            history=history_snapshot,
            model=model,
            max_tokens=max_tokens,
            temperature=0.6,
            timeout=timeout,
        )

        if answer is None:
            if thinking_msg:
                try:
                    await thinking_msg.delete()
                except Exception:
                    pass
            await interaction.followup.send(
                f"⚠️ ИИ не ответил за {timeout} сек. "
                f"Попробуйте позже или используйте `/ai long: True`."
            )
            # Улучшение №3 — фиксируем неудачу
            await track_ai_usage(interaction.user.id, channel_id, False)
            return

        hist = ai_chat_history[channel_id]
        hist.append({"role": "user", "content": prompt})
        hist.append({"role": "assistant", "content": answer})

    if thinking_msg:
        try:
            await thinking_msg.delete()
        except Exception:
            pass

    # Улучшение №3 — фиксируем успех
    await track_ai_usage(interaction.user.id, channel_id, True)

    chunks = [answer[i:i + 1900] for i in range(0, len(answer), 1900)] or ["(пустой ответ)"]
    header = f"**{interaction.user.display_name} → /ai**\n"
    first = header + chunks[0]
    if len(first) > 2000:
        first = first[:1990] + "…"

    try:
        await interaction.followup.send(first)
        for extra in chunks[1:]:
            await interaction.channel.send(extra)
    except discord.Forbidden:
        await interaction.followup.send("❌ Нет прав для отправки ответа.", ephemeral=True)
    except Exception as e:
        await log_error(interaction.client, "/ai.send", e)


@bot.tree.command(name="ai_reset", description="Сбросить историю диалога /ai в этом канале")
async def ai_reset(interaction: discord.Interaction):
    ai_chat_history.pop(interaction.channel_id, None)
    await interaction.response.send_message("🧹 История диалога /ai в этом канале очищена.",
                                            ephemeral=False)


# ============================================================
# МОДЕРАТОРЫ
# ============================================================
@bot.tree.command(name="moders", description="Список модераторов бота")
async def moders(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    mods = moders_store.read()
    if not mods:
        await interaction.followup.send("ℹ️ Модераторы не настроены.", ephemeral=True)
        return
    lines = []
    for uid in mods:
        member = interaction.guild.get_member(uid)
        name = member.mention if member else f"`{uid}`"
        if member and member.guild_permissions.administrator:
            name += " (админ)"
        lines.append(f"• {name}")
    await interaction.followup.send(
        f"🛠 **Модераторы ({len(mods)}):**\n" + "\n".join(lines), ephemeral=True)


@bot.tree.command(name="give", description="Выдать доступ к командам бота")
@app_commands.describe(user="Кому выдать доступ")
async def give_moders(interaction: discord.Interaction, user: discord.Member):
    if not admin_only(interaction):
        await interaction.response.send_message("❌ Только админ.", ephemeral=True)
        return

    def _add(d):
        if user.id not in d:
            d.append(user.id)
            return True
        return False
    added = await moders_store.update(_add)
    if added:
        await interaction.response.send_message(f"✅ {user.mention} получил доступ.")
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} уже имеет доступ.",
                                                ephemeral=True)


@bot.tree.command(name="take", description="Забрать доступ к командам бота")
@app_commands.describe(user="У кого забрать")
async def take_moders(interaction: discord.Interaction, user: discord.Member):
    if not admin_only(interaction):
        await interaction.response.send_message("❌ Только админ.", ephemeral=True)
        return

    def _rem(d):
        if user.id in d:
            d.remove(user.id)
            return True
        return False
    removed = await moders_store.update(_rem)
    if removed:
        await interaction.response.send_message(f"❌ {user.mention} лишён доступа.")
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} и так без доступа.",
                                                ephemeral=True)


# ============================================================
# АКТИВНОСТЬ
# ============================================================
def _get_steam_of(member: discord.Member) -> str:
    return links_store.read().get(str(member.id))


async def _activity_guard(interaction: discord.Interaction,
                          member: discord.Member, need_admin=True):
    if need_admin and not admin_only(interaction):
        await interaction.response.send_message("❌ Нужны права админа.", ephemeral=True)
        return None
    steam_id = _get_steam_of(member)
    if not steam_id:
        await interaction.response.send_message("❌ У игрока нет SteamID.", ephemeral=True)
        return None
    return steam_id


@bot.tree.command(name="activity_set", description="Установить часы активности")
@app_commands.describe(member="Участник", server="Сервер", hours="Часы")
async def activity_set(interaction: discord.Interaction, member: discord.Member,
                       server: str, hours: float):
    steam_id = await _activity_guard(interaction, member)
    if not steam_id:
        return
    if hours < 0:
        await interaction.response.send_message("❌ Часы < 0.", ephemeral=True)
        return

    def _set(db):
        profile = db.get(steam_id, {})
        activity = profile.get("activity", {})
        if not isinstance(activity, dict):
            activity = {}
        activity[server.upper()] = float(hours)
        profile.update(activity=activity, discord_id=str(member.id),
                       discord_name=member.display_name,
                       updated_at=now_utc().isoformat())
        db[steam_id] = profile
        return sum(float(v) for v in activity.values()
                   if isinstance(v, (int, float)))
    total = await players_store.update(_set)
    await interaction.response.send_message(
        f"✅ **{member.display_name}** - `{server.upper()}`: **{hours} ч.**\n"
        f"📊 Всего: {build_activity_bar(total, ACTIVITY_GOAL_HOURS)}",
        ephemeral=True)


@bot.tree.command(name="activity_clear", description="Сбросить активность игрока")
@app_commands.describe(member="Участник")
async def activity_clear(interaction: discord.Interaction, member: discord.Member):
    steam_id = await _activity_guard(interaction, member)
    if not steam_id:
        return

    def _clear(db):
        profile = db.get(steam_id, {})
        profile.update(activity={}, updated_at=now_utc().isoformat())
        db[steam_id] = profile
        return None
    await players_store.update(_clear)
    await interaction.response.send_message(
        f"✅ Активность {member.display_name} сброшена.", ephemeral=True)


@bot.tree.command(name="activity_show", description="Показать активность игрока")
@app_commands.describe(member="Участник")
async def activity_show(interaction: discord.Interaction, member: discord.Member):
    steam_id = await _activity_guard(interaction, member, need_admin=False)
    if not steam_id:
        return
    activity = players_store.read().get(steam_id, {}).get("activity", {})
    if not activity:
        await interaction.response.send_message(
            f"ℹ️ Активность {member.display_name} не введена.", ephemeral=True)
        return
    lines, total = [], 0.0
    for srv, hours in sorted(activity.items()):
        try:
            h = float(hours)
        except (ValueError, TypeError):
            continue
        total += h
        lines.append(f"• `{srv}`: **{h} ч.**")
    text = (f"📊 **Активность {member.display_name}:**\n\n" + "\n".join(lines)
            + f"\n\n**Итого:** {build_activity_bar(total, ACTIVITY_GOAL_HOURS)}")
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="activity_all", description="Активность всех с ролью")
async def activity_all(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    role = interaction.guild.get_role(ACTIVITY_ROLE_ID)
    if role is None:
        await interaction.followup.send(f"❌ Роль `{ACTIVITY_ROLE_ID}` не найдена.",
                                        ephemeral=True)
        return
    members = [m for m in role.members if not m.bot]
    if not members:
        await interaction.followup.send(f"ℹ️ У роли **{role.name}** нет участников.",
                                        ephemeral=True)
        return
    db, links = players_store.read(), links_store.read()
    data = []
    for member in members:
        steam_id = links.get(str(member.id))
        hours = 0.0
        if steam_id:
            activity = db.get(steam_id, {}).get("activity", {})
            if isinstance(activity, dict):
                for v in activity.values():
                    try:
                        hours += float(v)
                    except (ValueError, TypeError):
                        continue
        data.append((member, hours))
    data.sort(key=lambda x: x[1], reverse=True)
    lines = [f"{build_activity_bar(h, ACTIVITY_GOAL_HOURS)} - {m.mention}" for m, h in data]
    completed = sum(1 for _, h in data if h >= ACTIVITY_GOAL_HOURS)
    header = f"📊 **Активность роли {role.mention}**\n\n"
    footer = (f"\n\n📈 Всего: {len(data)}\n✅ Выполнили: {completed}\n"
              f"⚠️ Малоактивных: {len(data) - completed}")
    body = "\n".join(lines)
    if len(header + body + footer) <= 2000:
        await interaction.followup.send(header + body + footer)
    else:
        max_len = 2000 - len(header) - len(footer) - 100
        cut = body[:max_len]
        cut = cut[:cut.rfind("\n")]
        await interaction.followup.send(header + cut + "\n_...обрезано_" + footer)


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
    embed = discord.Embed(title="Официальные условия вступления в клан.", color=0x36393F)
    embed.description = (
        "Перед подачей заявки внимательно ознакомьтесь с нашими требованиями.\n"
        "Несоответствие любому из пунктов приведёт к отказу.\n\n"
        "**Общие требования:**\n"
        "• Отсутствие VAC-банов в Steam и блокировок на cs2red.ru.\n"
        "• Отсутствие членства в других кланах.\n"
        "• Возраст **от 12 лет**.\n\n"
        f"**Требования для {CLAN_NAME}:**\n"
        "• Рейтинг - **от 1.000 ммр**.\n"
        "• Онлайн - **не менее 3 часов в день**.\n\n"
        "**Что указать в заявке:**\n"
        "• Steam-профиль (ссылку или SteamID64)\n\n"
        "**Важно!**\n"
        "Если вам не напишут в течение 7 дней - заявка отклоняется.\n"
        "После принятия есть 2 дня на вступление.\n\n"
        "По вопросам вступления: обратитесь к администрации.")
    view = ClanView()
    view.add_item(discord.ui.Button(label=CLAN_NAME, url=CLAN_URL, row=1))
    await ctx.send(embed=embed, view=view)


# ============================================================
# ФОНОВЫЕ ЗАДАЧИ (с логированием ошибок)
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
        nick_to_steam = {p.get("cs2red_nick"): sid
                         for sid, p in db.items() if p.get("cs2red_nick")}
        last_seen = seen_store.read()

        seeded = last_seen.pop("_seeded", None)
        if not seeded:
            for sid in links.values():
                if sid in nick_to_steam:
                    continue
                u = await api.cs2red_user(sid)
                if u and u.get("nick"):
                    nick_to_steam[u["nick"]] = sid
                    db.setdefault(sid, {})["cs2red_nick"] = u["nick"]
            await players_store.save(db)

        now = now_utc().isoformat()
        matched = 0
        for nick, secs in online.items():
            steam_id = nick_to_steam.get(nick)
            if not steam_id:
                continue
            prev = last_seen.get(nick)
            if prev is not None and secs >= prev:
                delta = secs - prev
            elif prev is not None:
                delta = min(secs, ACTIVITY_TRACK_SECONDS * 1.5)
            else:
                delta = 0.0
            last_seen[nick] = secs
            if delta <= 0:
                continue
            profile = db.get(steam_id, {})
            activity = profile.get("activity", {})
            if not isinstance(activity, dict):
                activity = {}
            activity["AUTO"] = float(activity.get("AUTO", 0)) + delta / 3600.0
            profile.update(activity=activity, discord_name=profile.get("discord_name") or nick,
                           updated_at=now)
            db[steam_id] = profile
            matched += 1
        last_seen["_seeded"] = True
        if matched:
            await players_store.save(db)
            print(f"🕐 Трекер: +{matched} онлайн-игроков, время обновлено.")
        await seen_store.save(last_seen)
    except Exception as e:
        await log_error(bot, "activity_tracker", e)


@activity_tracker.before_loop
async def before_activity_tracker():
    await bot.wait_until_ready()


@tasks.loop(minutes=SYNC_INTERVAL_MINUTES)
async def auto_sync():
    try:
        print(f"\n⏰ Автосинхронизация - {now_utc().isoformat()}")
        links = links_store.read()
        guild = bot.get_guild(GUILD_ID)
        if not links or guild is None:
            return
        results = []
        for discord_id, steam_id in links.items():
            member = guild.get_member(int(discord_id))
            if member is None:
                continue
            try:
                results.append(await sync_role_by_id(guild, member, steam_id))
                results.append(await sync_clan_role_by_id(guild, member, steam_id))
            except Exception as e:
                await log_error(bot, f"auto_sync:{discord_id}", e)
            await asyncio.sleep(REQUEST_DELAY)
        changes = [r for r in results if r.startswith(("✅", "🔄", "👥"))]
        if changes:
            await log_to_channel(bot, "⏰ **Автосинхронизация**\n" + "\n".join(changes[:30]))
    except Exception as e:
        await log_error(bot, "auto_sync", e)


@auto_sync.error
async def auto_sync_error(error):
    await log_error(bot, "auto_sync.error", error)


@tasks.loop(hours=BAN_CHECK_INTERVAL_HOURS)
async def ban_check():
    try:
        print(f"\n🔨 Проверка банов - {now_utc().isoformat()}")
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            return
        actions = await check_punishment_roles(bot, guild, "ban")
        if actions:
            await log_to_channel(bot, "🔨 **Проверка банов:**\n" + "\n".join(actions))
    except Exception as e:
        await log_error(bot, "ban_check", e)


@ban_check.error
async def ban_check_error(error):
    await log_error(bot, "ban_check.error", error)


@tasks.loop(hours=MUTE_CHECK_INTERVAL_HOURS)
async def mute_check():
    try:
        print(f"\n🔇 Проверка мутов - {now_utc().isoformat()}")
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            return
        actions = await check_punishment_roles(bot, guild, "mute")
        if actions:
            await log_to_channel(bot, "🔇 **Проверка мутов:**\n" + "\n".join(actions))
    except Exception as e:
        await log_error(bot, "mute_check", e)


@mute_check.error
async def mute_check_error(error):
    await log_error(bot, "mute_check.error", error)


async def _align_to_half_hour(minutes: int):
    await bot.wait_until_ready()
    now = now_utc()
    target_min = 0 if minutes == 0 else 30
    if now.minute < target_min:
        target = now.replace(minute=target_min, second=0, microsecond=0)
    else:
        target = (now + datetime.timedelta(hours=1)).replace(
            minute=target_min, second=0, microsecond=0)
    wait = (target - now).total_seconds()
    if wait > 0:
        await asyncio.sleep(wait)


async def before_ban_check():
    await _align_to_half_hour(0)


async def before_mute_check():
    await _align_to_half_hour(30)


ban_check.before_loop(before_ban_check)
mute_check.before_loop(before_mute_check)


@auto_sync.before_loop
async def before_auto_sync():
    await bot.wait_until_ready()
    # Улучшение №1 — джиттер, чтобы задачи не совпадали
    delay = random.randint(0, 120)
    print(f"⏰ auto_sync: старт через {delay} сек.")
    await asyncio.sleep(delay)


# ============================================================
# ИИ-АНАЛИЗ РАЗ В ЧАС (со статистикой /ai)
# ============================================================
AI_SYSTEM_PROMPT = (
    "Ты — технический аналитик Discord-бота. Тебе дают метрики работы "
    "бота и статистику по его задачам. Твоя задача — оценить, насколько "
    "поведение бота выглядит «роботизированным» (автоматизированным, "
    "по расписанию, без вариативности), выявить риски и предложить "
    "краткие улучшения. Отвечай СЖАТО на русском языке, без воды, "
    "по пунктам, не более 900 токенов."
)

_FIRST_AI_REPORT_DONE = False


def _collect_runtime_stats() -> dict:
    links = links_store.read()
    players = players_store.read()
    bans = bans_store.read()
    moders = moders_store.read()
    votes = votes_store.read()
    ai_st = ai_stats_store.read()

    now = now_utc()
    active_temp_bans = 0
    perm_bans = 0
    for entry in bans.values():
        if not isinstance(entry, dict):
            continue
        t = entry.get("type")
        if t == "perm":
            perm_bans += 1
        elif t == "temp":
            try:
                until = datetime.datetime.fromisoformat(entry.get("until") or "")
                if until.tzinfo is None:
                    until = until.replace(tzinfo=UTC)
                if until > now:
                    active_temp_bans += 1
            except Exception:
                pass

    guild = bot.get_guild(GUILD_ID) if GUILD_ID else None
    members_total = guild.member_count if guild else 0

    total_hours = 0.0
    active_players = 0
    for p in players.values():
        act = p.get("activity") if isinstance(p, dict) else None
        if isinstance(act, dict) and act:
            active_players += 1
            for v in act.values():
                try:
                    total_hours += float(v)
                except (TypeError, ValueError):
                    continue

    return {
        "uptime_sec": int(time.time() - BOT_START_TIME),
        "ws_latency_ms": round(bot.latency * 1000, 1),
        "guild_members": members_total,
        "linked_users": len(links),
        "players_in_db": len(players),
        "active_players": active_players,
        "total_tracked_hours": round(total_hours, 2),
        "moderators_count": len(moders),
        "votes_records": len(votes),
        "perm_bans": perm_bans,
        "active_temp_bans": active_temp_bans,
        "ai_channels_with_history": len(ai_chat_history),
        # Улучшение №3 — статистика /ai
        "ai_total": int(ai_st.get("total", 0)),
        "ai_success": int(ai_st.get("success", 0)),
        "ai_fail": int(ai_st.get("fail", 0)),
        "tasks_running": {
            "auto_sync": auto_sync.is_running(),
            "ban_check": ban_check.is_running(),
            "mute_check": mute_check.is_running(),
            "activity_tracker": activity_tracker.is_running(),
            "ai_script_analysis": ai_script_analysis.is_running(),
        },
        "sync_interval_min": SYNC_INTERVAL_MINUTES,
        "ban_interval_h": BAN_CHECK_INTERVAL_HOURS,
        "mute_interval_h": MUTE_CHECK_INTERVAL_HOURS,
        "activity_track_sec": ACTIVITY_TRACK_SECONDS,
        "ai_interval_min": AI_ANALYSIS_INTERVAL_MINUTES,
    }


def _build_ai_prompt(stats: dict, prev_report: str | None = None) -> str:
    lines = [
        "Проанализируй работу Discord-бота клана (Quantum).",
        "",
        "=== МЕТРИКИ ===",
        f"Аптайм (сек): {stats['uptime_sec']}",
        f"WS-задержка (мс): {stats['ws_latency_ms']}",
        f"Участников на сервере: {stats['guild_members']}",
        f"Привязанных Discord↔Steam: {stats['linked_users']}",
        f"Игроков в БД: {stats['players_in_db']} (с активностью: {stats['active_players']})",
        f"Всего учтённых часов: {stats['total_tracked_hours']}",
        f"Модераторов: {stats['moderators_count']}",
        f"Голосований: {stats['votes_records']}",
        f"Перм. запретов: {stats['perm_bans']}",
        f"Активных временных: {stats['active_temp_bans']}",
        f"Каналов с историей /ai: {stats['ai_channels_with_history']}",
        f"Запросов /ai: {stats['ai_total']} (ok {stats['ai_success']}, fail {stats['ai_fail']})",
        "",
        "=== ФОНОВЫЕ ЗАДАЧИ ===",
    ]
    for name, running in stats["tasks_running"].items():
        lines.append(f"- {name}: {'запущена' if running else 'ОСТАНОВЛЕНА'}")
    lines += [
        f"- auto_sync: каждые {stats['sync_interval_min']} мин",
        f"- ban_check: каждые {stats['ban_interval_h']} ч",
        f"- mute_check: каждые {stats['mute_interval_h']} ч",
        f"- activity_tracker: каждые {stats['activity_track_sec']} сек",
        f"- ai_script_analysis: каждые {stats['ai_interval_min']} мин",
        "",
        "=== ЗАДАНИЕ ===",
        "1) Оцени «роботизированность» бота по шкале 0-10. Объясни 2-3 пунктами.",
        "2) Укажи 3 главных риска.",
        "3) Дай 3-4 коротких улучшения.",
        "4) Итог в 1-2 строки.",
    ]
    if prev_report:
        lines += ["", "=== ПРЕДЫДУЩИЙ ОТЧЁТ ===", prev_report[:1500]]
    return "\n".join(lines)


async def _run_ai_analysis_once() -> str | None:
    global _FIRST_AI_REPORT_DONE
    stats = _collect_runtime_stats()
    prev = None
    try:
        prev_path = data_path("ai_last_report.txt")
        if prev_path.exists():
            prev = prev_path.read_text(encoding="utf-8")
    except Exception:
        prev = None

    prompt = _build_ai_prompt(stats, prev)
    answer, source = await ai_chat_with_fallback(
        prompt=prompt, system=AI_SYSTEM_PROMPT, history=None,
        model="default", max_tokens=700, temperature=0.4, timeout=45)

    if answer is None and not _FIRST_AI_REPORT_DONE:
        print("🤖 Первый ИИ-анализ: LLM7 недоступен, отчёт пропущен.")
        _FIRST_AI_REPORT_DONE = True
        return None
    _FIRST_AI_REPORT_DONE = True

    channel = bot.get_channel(AI_REPORT_CHANNEL_ID)
    if channel is None:
        await log_error(bot, "ai_report", f"Канал {AI_REPORT_CHANNEL_ID} не найден")
        return None

    if answer is None:
        embed = discord.Embed(
            title="🤖 ИИ-анализ недоступен",
            description="LLM7 не ответил. Сырые метрики ниже.",
            color=0xED4245, timestamp=now_utc())
    else:
        embed = discord.Embed(title="🤖 ИИ-анализ работы бота (Quantum)",
                              color=0x5865F2, timestamp=now_utc())
        embed.description = answer[:4000]

    uptime = stats["uptime_sec"]
    d, r = divmod(uptime, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    uptime_str = f"{d}д {h}ч {m}м"

    embed.add_field(name="⏱ Аптайм", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="📡 WS-пинг", value=f"`{stats['ws_latency_ms']} мс`", inline=True)
    embed.add_field(name="👥 Привязано", value=f"`{stats['linked_users']}`", inline=True)
    embed.add_field(name="🧩 Задач активно",
                    value=f"`{sum(1 for v in stats['tasks_running'].values() if v)}/5`",
                    inline=True)
    embed.add_field(name="🚫 Запретов",
                    value=f"`perm: {stats['perm_bans']} / temp: {stats['active_temp_bans']}`",
                    inline=True)
    embed.add_field(name="🤖 /ai",
                    value=f"`{stats['ai_success']}/{stats['ai_fail']}`",
                    inline=True)

    if bot.user:
        embed.set_footer(text=f"Quantum AI Monitor • {utc_stamp()} (UTC)",
                         icon_url=bot.user.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except Exception as e:
        await log_error(bot, "ai_report.send", e)
        return None

    if answer:
        try:
            data_path("ai_last_report.txt").write_text(answer, encoding="utf-8")
        except Exception:
            pass
    return answer


@tasks.loop(minutes=AI_ANALYSIS_INTERVAL_MINUTES)
async def ai_script_analysis():
    try:
        print(f"\n🤖 ИИ-анализ бота - {now_utc().isoformat()}")
        await _run_ai_analysis_once()
    except Exception as e:
        await log_error(bot, "ai_script_analysis", e)


@ai_script_analysis.before_loop
async def before_ai_script_analysis():
    await bot.wait_until_ready()
    await asyncio.sleep(180)


@ai_script_analysis.error
async def ai_script_analysis_error(error):
    await log_error(bot, "ai_script_analysis.error", error)


@bot.tree.command(name="ai_report", description="Запустить ИИ-анализ бота вручную")
async def ai_report(interaction: discord.Interaction):
    if not await _admin_guard(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send("🤖 Запускаю анализ…", ephemeral=True)
    asyncio.create_task(_run_ai_analysis_once())


# ============================================================
# HTTP-СЕРВЕР ДЛЯ RENDER
# ============================================================
app = Flask(__name__)


@app.route('/')
def health():
    return "Bot is running"


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN не задан в .env!")
    elif GUILD_ID == 0:
        print("❌ GUILD_ID не задан в .env!")
    else:
        threading.Thread(target=run_health_server, daemon=True).start()
        bot.run(DISCORD_TOKEN)
