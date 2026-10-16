"""
Quantum - бот клана (v28: ИИ-контекст, дашборд, быстрые запросы)
"""
import os
import re
import json
import time
import random
import asyncio
import datetime
import platform
import shutil
import sys
import threading
import traceback
from pathlib import Path
from collections import deque

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from flask import Flask

try:
    import ai_rules
except Exception as _ai_import_error:
    ai_rules = None
    _AI_IMPORT_ERROR = f"{type(_ai_import_error).__name__}: {_ai_import_error}"
else:
    _AI_IMPORT_ERROR = ""

try:
    import github_sync as github_sync_module
except Exception as _gh_import_error:
    github_sync_module = None
    _GH_IMPORT_ERROR = f"{type(_gh_import_error).__name__}: {_gh_import_error}"
else:
    _GH_IMPORT_ERROR = ""

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("PYTHONUNBUFFERED", "1")

load_dotenv()


def _resolve_data_dir() -> Path:
    candidates = [Path(os.getenv("DATA_DIR", ".")).resolve(),
                  Path(__file__).resolve().parent]
    first = True
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except Exception as e:
            print(f"⚠️ Папка данных {candidate} недоступна: {e}", flush=True)
            first = False
            continue
        if not first:
            print(f"⚠️ Использую папку данных: {candidate}", flush=True)
        return candidate
    print("⚠️ Не нашёл доступную папку данных, работаю в текущем каталоге", flush=True)
    return Path.cwd()


def _seed_data_dir_from_script_dir():
    script_dir = Path(__file__).resolve().parent
    if DATA_DIR == script_dir:
        return
    copied = []
    for pattern in ("*.json", "rules.txt"):
        for src in sorted(script_dir.glob(pattern)):
            dst = DATA_DIR / src.name
            if dst.exists():
                continue
            try:
                shutil.copyfile(src, dst)
                copied.append(src.name)
            except Exception as e:
                print(f"⚠️ не скопировал {src.name} в папку данных: {e}", flush=True)
    if copied:
        print("📦 В папку данных перенесено из репозитория: " + ", ".join(copied), flush=True)


DATA_DIR = _resolve_data_dir()
_seed_data_dir_from_script_dir()


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


def _env_ids(name: str, default: str = "") -> list:
    raw = (os.getenv(name) or default or "").replace(";", ",").replace(" ", ",")
    result: list = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            log(f"⚠️ {name}: '{part}' не число — пропускаю")
            continue
        if value and value not in result:
            result.append(value)
    return result


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log(f"⚠️ {name}='{raw}' не число — беру {default}")
        return default


GUILD_ID = _env_int("GUILD_ID", 0)

LOG_CHANNEL_ID = _env_int("LOG_CHANNEL_ID", 1511463623703265361)
APPLICATION_LOGS_CHANNEL_ID = _env_int("APPLICATION_LOGS_CHANNEL_ID", LOG_CHANNEL_ID)
APPLICATIONS_CHANNEL_ID = _env_int("APPLICATIONS_CHANNEL_ID", 1511463623703265361)
APPS_LOG_CHANNEL_ID = _env_int("APPS_LOG_CHANNEL_ID", 1511463623703265361)
UNLINKED_CHANNEL_ID = _env_int("UNLINKED_CHANNEL_ID", 1555204495682568202)
SYNC_LOG_CHANNEL_ID = _env_int("SYNC_LOG_CHANNEL_ID", 0) or UNLINKED_CHANNEL_ID
THREADS_CHANNEL_ID = _env_int("THREADS_CHANNEL_ID", 1236678127778795660)
DB_CHANNEL_ID = _env_int("DB_CHANNEL_ID", 1554883485834149888)
ERROR_LOG_CHANNEL_ID = _env_int("ERROR_LOG_CHANNEL_ID", 1511463623703265361)

# Дашборд идёт в канал DB_CHANNEL_ID.
DASHBOARD_CHANNEL_ID = DB_CHANNEL_ID

AI_LOG_CHANNEL_ID = _env_int("AI_LOG_CHANNEL_ID",
                             _env_int("AI_REPORT_CHANNEL_ID", 1556427610160889907))

PANEL_CHANNEL_ID = _env_int("PANEL_CHANNEL_ID", 1554796338661826660)

ALLOWED_ROLE_ID = _env_int("ALLOWED_ROLE_ID", 0)
DEPUTY_ROLE_IDS = _env_ids("DEPUTY_ROLE_IDS") or _env_ids("DEPUTY_ROLE_ID")
DEPUTY_ROLE_ID = DEPUTY_ROLE_IDS[0] if DEPUTY_ROLE_IDS else 0

THREAD_KEEP_IDS = _env_ids("THREAD_KEEP_IDS")
THREAD_REMOVE_IDS = _env_ids("THREAD_REMOVE_IDS")
REVIEWER_ROLE_ID_2 = _env_int("REVIEWER_ROLE_ID_2", 0)
SPAM_VOTE_ROLE_ID = _env_int("SPAM_VOTE_ROLE_ID", 0)
EXTRA_REVIEWER_ROLE_1 = _env_int("EXTRA_REVIEWER_ROLE_1", 0)
EXTRA_REVIEWER_ROLE_2 = _env_int("EXTRA_REVIEWER_ROLE_2", 0)
EXTRA_REVIEWER_ROLE_3 = _env_int("EXTRA_REVIEWER_ROLE_3", 0)

AUTO_ROLE_ID = _env_int("AUTO_ROLE_ID", 0)
BYPASS_ROLE_ID = _env_int("BYPASS_ROLE_ID", 0)
NO_COOLDOWN_ROLE_ID = _env_int("NO_COOLDOWN_ROLE_ID", 0)

ACTIVITY_ROLE_ID = _env_int("ACTIVITY_ROLE_ID", 1448368118190837800)

CLAN_NAME = os.getenv("CLAN_NAME", "TALENT")
CLAN_URL = os.getenv("CLAN_URL", "https://cs2red.ru/clans/id/47")
VOTES_REQUIRED = max(1, _env_int("VOTES_REQUIRED", 1))

LINK_COOLDOWN_SECONDS = max(0, _env_int("LINK_COOLDOWN_SECONDS", 30))
LINK_VERIFY = _env_int("LINK_VERIFY", 1) == 1
LINK_CODE_TTL_MINUTES = max(1, _env_int("LINK_CODE_TTL_MINUTES", 20))

# ============================================================
# ИИ
# ============================================================
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
AI_ENABLED = _env_int("AI_ENABLED", 1) == 1
AI_MODEL = (os.getenv("AI_MODEL") or "").strip()
AI_API_URL = (os.getenv("AI_API_URL") or "").strip()
AI_PROVIDER = (os.getenv("AI_PROVIDER") or "auto").strip().lower()
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "").strip()
AI_API_KEY_ALT = (os.getenv("AI_API_KEY") or os.getenv("LLM7_API_KEY")
                  or os.getenv("OPENROUTER_API_KEY") or "").strip()
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT") or 45)
AI_MAX_OUTPUT_TOKENS = _env_int("AI_MAX_OUTPUT_TOKENS", 900)
AI_THINKING_LEVEL = (os.getenv("AI_THINKING_LEVEL") or "").strip()
AI_ERROR_INTERVAL_MINUTES = max(1, _env_int("AI_ERROR_INTERVAL_MINUTES", 15))
AI_ERROR_ANALYSIS = _env_int("AI_ERROR_ANALYSIS", 1) == 1
AI_ASK_COOLDOWN_SECONDS = max(0, _env_int("AI_ASK_COOLDOWN_SECONDS", 20))
RULES_URL = (os.getenv("RULES_URL") or "https://cs2red.ru/rules").strip()
RULES_API_URL = (os.getenv("RULES_API_URL") or "").strip()
RULES_TTL_HOURS = max(1, _env_int("RULES_TTL_HOURS", 12))

# ============================================================
# GITHUB
# ============================================================
GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
GITHUB_REPO = (os.getenv("GITHUB_REPO") or "").strip()
GITHUB_BRANCH = (os.getenv("GITHUB_BRANCH") or "main").strip()
GITHUB_DATA_PATH = (os.getenv("GITHUB_DATA_PATH") or "").strip()
GITHUB_PUSH_INTERVAL_SECONDS = max(30, _env_int("GITHUB_PUSH_INTERVAL_SECONDS", 120))
GITHUB_PULL_OVERWRITE = _env_int("GITHUB_PULL_OVERWRITE", 0) == 1
GITHUB_SYNC_FILES = [s.strip() for s in (os.getenv("GITHUB_SYNC_FILES") or (
    "links.json,users_db.json,moderators.json,votes.json,"
    "setup.json,pending_links.json,rules.txt")).split(",") if s.strip()]
GITHUB_LOG_INTERVAL_SECONDS = max(60, _env_int("GITHUB_LOG_INTERVAL_SECONDS", 3600))

ACTIVITY_GOAL_HOURS = 8
ACTIVITY_MIN_HOURS = 8
APPLY_EMBED_COLOR = 0x2B2D31
AI_EMBED_COLOR = 0x000000

BOT_START_TIME = time.time()
CMD_API_TIMEOUT = 30.0
CS2RED_AUTH_BLOCK_SECONDS = max(30, _env_int("CS2RED_AUTH_BLOCK_SECONDS", 600))

# ============================================================
# ЗАДЕРЖКИ (ускорено)
# ============================================================
SYNC_INTERVAL_MINUTES = max(1, _env_int("SYNC_INTERVAL_MINUTES", 360))
ACTIVITY_TRACK_SECONDS = max(60, _env_int("ACTIVITY_TRACK_SECONDS", 900))
ACTIVITY_TRACK_DELTA = 300
CLANS_CACHE_TTL = 300

REQUEST_DELAY = 0.1
SYNC_BTN_DELAY = max(1, _env_int("SYNC_BTN_DELAY", 1))
LINK_ALL_DELAY = max(1, _env_int("LINK_ALL_DELAY", 1))
SYNC_CMD_DELAY = max(1, _env_int("SYNC_CMD_DELAY", 1))
DASHBOARD_INTERVAL_MINUTES = max(1, _env_int("DASHBOARD_INTERVAL_MINUTES", 10))


def _parse_cookies(raw: str) -> dict:
    result: dict = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 7 and parts[5].strip() and parts[6].strip():
                result[parts[5].strip()] = parts[6].strip()
            continue
        for part in line.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, _, value = part.partition("=")
            name, value = name.strip(), value.strip()
            if name and value:
                result[name] = value
    return result


_cookies_from_string = _parse_cookies(os.getenv("CS2RED_COOKIE_STRING", ""))

_cookie_env = {
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
}
CS2RED_COOKIES = {k: v for k, v in _cookies_from_string.items() if v}
for _cookie_name, _cookie_value in _cookie_env.items():
    if _cookie_value and not CS2RED_COOKIES.get(_cookie_name):
        CS2RED_COOKIES[_cookie_name] = _cookie_value

# ВАЖНО: без "br" в Accept-Encoding. cs2red отдаёт Brotli, а aiohttp не умеет
# его распаковывать без доп. библиотеки. Без "br" сервер отдаёт gzip/deflate.
CS2RED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/154.0.0.0 Safari/537.36 Brave/154.0.0.0",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://cs2red.ru/admin",
    "Origin": "https://cs2red.ru",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
    "Connection": "keep-alive",
}

DEFAULT_ROLE_MAP = {
    1: None,
    2: "VIP",
    3: "Premium",
    4: "Moderator",
    5: "Администратор",
    6: "Амбассадор",
    7: "Спонсор",
    9: "Plus",
    13: "Гл.Модератор",
}
ROLE_DISPLAY_MAP = {1: "Мл. Модер", 3: "Модератор", 5: "Админ",
                    6: "С. Админ", 7: "Спонсор", 13: "Гл.Модератор"}


def _load_role_map() -> dict:
    result = dict(DEFAULT_ROLE_MAP)
    raw = (os.getenv("ROLE_MAP_JSON") or "").strip()
    if not raw:
        return result
    try:
        extra = json.loads(raw)
        if not isinstance(extra, dict):
            raise ValueError("ожидается JSON-объект")
        for key, value in extra.items():
            result[int(key)] = None if value is None or str(value).strip().lower() in ("", "none", "null") \
                else str(value)
    except Exception as e:
        log(f"⚠️ ROLE_MAP_JSON: {e} — работаю на встроенной карте")
    return result


ROLE_MAP = _load_role_map()
ROLE_NAMES = {n for n in ROLE_MAP.values() if n}


def _load_role_ids() -> dict:
    raw = (os.getenv("ROLE_IDS_JSON") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("ожидается JSON-объект")
        return {str(k): int(v) for k, v in data.items()}
    except Exception as e:
        log(f"⚠️ ROLE_IDS_JSON: {e} — ищу роли по имени")
        return {}


ROLE_IDS = _load_role_ids()


def resolve_managed_role(guild, name: str):
    rid = ROLE_IDS.get(name)
    if rid:
        role = guild.get_role(rid)
        if role:
            return role
        log(f"⚠️ ROLE_IDS_JSON: роль {rid} ('{name}') не найдена в гильдии")
    norm = name.strip().casefold()
    for role in guild.roles:
        if role.name.strip().casefold() == norm:
            return role
    return None


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


# ============================================================
# ХРАНИЛИЩЕ JSON
# ============================================================
class JsonStore:
    def __init__(self, path, default):
        self.path = Path(path)
        self.default = default
        self.lock = asyncio.Lock()
        self._cache = None
        self._stamp = None

    def _default_value(self):
        return self.default() if callable(self.default) else self.default

    def _load(self):
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            self._cache, self._stamp = self._default_value(), None
            return self._cache
        if self._cache is not None and self._stamp == stamp:
            return self._cache
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log(f"⚠️ {self.path.name}: {e} — беру значение по умолчанию")
            data = self._default_value()
        self._cache, self._stamp = data, stamp
        return data

    def _dump(self, data):
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self._cache = data
        try:
            st = self.path.stat()
            self._stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            self._stamp = None
        try:
            _mark_data_dirty(self.path.name)
        except Exception:
            pass

    def read(self):
        return self._load()

    def invalidate(self):
        self._cache = None
        self._stamp = None

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
pending_store = JsonStore(data_path("pending_links.json"), dict)
setup_store = JsonStore(data_path("setup.json"), dict)


# ============================================================
# ИИ И ПРАВИЛА
# ============================================================
ai_client = None
rules_base = None

if ai_rules is not None:
    rules_base = ai_rules.RulesBase(
        DATA_DIR,
        url=RULES_URL,
        api_url=RULES_API_URL,
        cookies=CS2RED_COOKIES or None,
        headers=CS2RED_HEADERS,
        ttl_hours=RULES_TTL_HOURS,
    )
    rules_base.load_cache()
    if AI_ENABLED:
        ai_client = ai_rules.make_ai_client(
            AI_PROVIDER,
            gemini_key=GEMINI_API_KEY,
            openai_key=AI_API_KEY_ALT,
            model=AI_MODEL,
            base_url=AI_BASE_URL,
            api_url=AI_API_URL,
            timeout=AI_TIMEOUT,
            max_output_tokens=AI_MAX_OUTPUT_TOKENS,
            thinking_level=AI_THINKING_LEVEL,
        )
    log(f"🤖 ИИ: {ai_client.status_line() if ai_client else 'выключен'}")
    log(f"📚 Правила: {rules_base.status_line()}")
else:
    log(f"⚠️ ai_rules.py не загружен: {_AI_IMPORT_ERROR}")

_error_ring = deque(maxlen=60)
_ai_last_error_report = 0.0
_ai_ask_last: dict = {}

# Контекст диалога ИИ: channel_id -> deque последних сообщений
_ai_context: dict = {}
_AI_CONTEXT_MAX = 5

_data_dirty: set = set()


def _mark_data_dirty(filename: str):
    _data_dirty.add(str(filename))


github_sync = None
if github_sync_module is not None:
    github_sync = github_sync_module.GitHubSync(
        GITHUB_TOKEN, GITHUB_REPO,
        branch=GITHUB_BRANCH, base_path=GITHUB_DATA_PATH,
    )
    log(f"☁️ GitHub-хранилище: {github_sync.status_line()}")
else:
    log(f"⚠️ github_sync.py не загружен: {_GH_IMPORT_ERROR}")


async def pull_data_from_github() -> str:
    if github_sync is None or not github_sync.enabled:
        return "выключено"
    if api.session is None:
        return "нет HTTP-сессии"
    try:
        pulled = await github_sync.pull(api.session, GITHUB_SYNC_FILES, DATA_DIR,
                                        overwrite=GITHUB_PULL_OVERWRITE)
    except Exception as e:
        await log_error(bot, "pull_data_from_github", e)
        return f"ошибка: {e}"
    if not pulled:
        return "нечего подтягивать"
    for store in (links_store, players_store, bans_store, moders_store,
                  votes_store, seen_store, pending_store, setup_store):
        try:
            store.invalidate()
        except Exception:
            pass
    return "подтянуто: " + ", ".join(pulled)


def _write_error_to_file(context: str, exc):
    try:
        ts = now_utc().strftime("%Y-%m-%d %H:%M:%S")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) \
            if isinstance(exc, BaseException) else str(exc)
        path = data_path("error_log.txt")
        try:
            if path.exists() and path.stat().st_size > 1_000_000:
                path.replace(path.with_name("error_log.old.txt"))
        except OSError:
            pass
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {context}\n{tb}\n{'=' * 60}\n")
    except Exception as e:
        log(f"⚠️ error_log: {e}")


NET_ERRORS = (
    aiohttp.ClientConnectorError,
    aiohttp.ClientOSError,
    aiohttp.ServerTimeoutError,
    asyncio.TimeoutError,
)


def _remember_error(context: str, exc):
    if isinstance(exc, BaseException):
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        name = f"{type(exc).__name__}: {exc}"
    else:
        tb = str(exc)
        name = str(exc)
    _error_ring.append({
        "time": now_utc().strftime("%d.%m %H:%M:%S"),
        "ts": time.time(),
        "context": str(context),
        "error": name[:500],
        "traceback": tb[-2000:],
    })


async def ai_log(text: str, title: str = ""):
    log(f"🤖 {text}")
    if not AI_LOG_CHANNEL_ID:
        return
    try:
        channel = bot.get_channel(AI_LOG_CHANNEL_ID)
    except Exception:
        channel = None
    if channel is None:
        return
    if not title:
        title = (text.split("\n", 1)[0] or "Лог ИИ")[:250]
    description = text if len(text) <= 4000 else text[:4000] + "…"
    embed = discord.Embed(title=title, description=description,
                          color=AI_EMBED_COLOR, timestamp=now_utc())
    embed.set_footer(text="Quantum • AI Logs")
    try:
        await safe_send(channel, embed=embed)
    except Exception as e:
        log(f"⚠️ не отправил эмбед ИИ: {e}")


async def ai_log_embed(title: str, description: str, footer: str = ""):
    log(f"🤖 {title}: {description[:160]}")
    if not AI_LOG_CHANNEL_ID:
        return
    try:
        channel = bot.get_channel(AI_LOG_CHANNEL_ID)
    except Exception:
        channel = None
    if channel is None:
        return
    embed = discord.Embed(title=title[:250], description=(description or "—")[:4000],
                          color=AI_EMBED_COLOR, timestamp=now_utc())
    if footer:
        embed.set_footer(text=footer[:2000])
    try:
        await safe_send(channel, embed=embed)
    except Exception as e:
        log(f"⚠️ не отправил эмбед ИИ: {e}")


def _bot_stats_line() -> str:
    up = int(time.time() - BOT_START_TIME)
    days, rem = divmod(up, 86400)
    hours, rem = divmod(rem, 3600)
    uptime = f"{days} д. {hours} ч." if days else f"{hours} ч. {rem // 60} мин."
    running = 0
    for task_obj in (activity_tracker, rules_refresher,
                     ai_error_watcher, data_push_loop, dashboard_loop):
        try:
            running += 1 if task_obj.is_running() else 0
        except Exception:
            pass
    try:
        links_count = len(links_store.read())
    except Exception:
        links_count = 0
    ws = bot.latency * 1000 if bot.is_ready() else 0
    return (f"Quantum • аптайм {uptime} • WS {ws:.0f} мс • "
            f"привязок {links_count} • задач {running}/5 • ошибок в буфере {len(_error_ring)}")


async def log_error(bot: commands.Bot, context: str, exc):
    _write_error_to_file(context, exc)
    _remember_error(context, exc)
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
# ЗАЩИТА ОТ ФЛУДА
# ============================================================
_send_lock = asyncio.Lock()
_send_timestamps = deque()


async def _rate_limit_send():
    async with _send_lock:
        while True:
            now = time.time()
            while _send_timestamps and now - _send_timestamps[0] > 1.0:
                _send_timestamps.popleft()
            if len(_send_timestamps) < 3:
                _send_timestamps.append(now)
                return
            await asyncio.sleep(max(0.01, 1.0 - (now - _send_timestamps[0])))


async def safe_send(target, *args, retries: int = 5, **kwargs):
    await _rate_limit_send()
    last_exc = None
    for attempt in range(retries):
        try:
            return await target.send(*args, **kwargs)
        except discord.Forbidden as e:
            log(f"❌ safe_send: нет прав на отправку в "
                f"{getattr(target, 'id', '?')}: {e}")
            return None
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
                           interaction: discord.Interaction, context: str = ""):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        await log_error(bot, context or "run_with_timeout",
                        TimeoutError(f"внешний вызов не ответил за {timeout:.0f} сек"))
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
        self.sem = asyncio.Semaphore(4)   # больше параллельных запросов
        self._clans_cache = {"ts": 0.0, "data": None}
        self.last_status: int | None = None
        self._auth_block_until = 0.0
        self._last_403_log = 0.0
        self._403_count = 0

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

    def auth_blocked(self) -> bool:
        return time.time() < self._auth_block_until

    def _note_403(self, url: str, body: str = ""):
        now = time.time()
        self._403_count += 1
        if "/admin/" in url:
            self._auth_block_until = now + CS2RED_AUTH_BLOCK_SECONDS

        if body:
            snippet = body[:300].replace("\n", " ").replace("\r", "")
            log(f"🔴 403 body от {url}: {snippet}")

        if now - self._last_403_log > 60:
            self._last_403_log = now
            low = body.lower()
            if "cf-ray" in low or "cloudflare" in low or "just a moment" in low:
                hint = "Cloudflare (IP Render заблокирован)"
            elif body.startswith("{") or body.startswith("["):
                hint = "API вернул JSON-ошибку (проверь cookie/права)"
            else:
                hint = "неизвестно (смотри тело выше)"
            log(f"🔴 403 на {url} (всего {self._403_count} раз за сессию). "
                f"Похоже на: {hint}")

    async def _get_json(self, url, params=None, force: bool = False):
        if not self.session:
            return None
        if not force and "/admin/" in url and self.auth_blocked():
            return None
        for attempt in range(2):
            try:
                async with self.sem:
                    async with self.session.get(url, params=params) as r:
                        self.last_status = r.status
                        if r.status == 403:
                            body = await r.text()
                            self._note_403(url, body)
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

    async def player_clan(self, steam_id: str, user: dict | None = None):
        if user is None:
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
        if data is None:
            return None
        players = ((data.get("response") or {}).get("players")) or []
        return players[0] if players else {}

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
def is_moderator(user_id: int, guild: discord.Guild | None) -> bool:
    if user_id in moders_store.read():
        return True
    if guild is None:
        return False
    member = guild.get_member(user_id)
    return bool(member and member.guild_permissions.administrator)


def get_all_reviewer_role_ids() -> list:
    return [ALLOWED_ROLE_ID, DEPUTY_ROLE_ID, REVIEWER_ROLE_ID_2, SPAM_VOTE_ROLE_ID,
            EXTRA_REVIEWER_ROLE_1, EXTRA_REVIEWER_ROLE_2, EXTRA_REVIEWER_ROLE_3] \
        + list(DEPUTY_ROLE_IDS)


def _has_any_role(member, role_ids) -> bool:
    return any(r.id in role_ids for r in member.roles)


def user_can_review(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_any_role(
        member, set(get_all_reviewer_role_ids()))


def user_can_spam_vote(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_any_role(
        member, {SPAM_VOTE_ROLE_ID})


def user_can_decide_solo(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    ids = {rid for rid in (set(DEPUTY_ROLE_IDS) | {DEPUTY_ROLE_ID}) if rid}
    return _has_any_role(member, ids)


def collect_thread_keep_ids(guild: discord.Guild) -> set:
    ids = set()
    for rid in DEPUTY_ROLE_IDS:
        role = guild.get_role(rid) if rid else None
        if role:
            ids.update(m.id for m in role.members)
    ids.update(THREAD_KEEP_IDS)
    if guild.me:
        ids.add(guild.me.id)
    return ids - set(THREAD_REMOVE_IDS)


def has_bypass_role(member) -> bool:
    if not BYPASS_ROLE_ID:
        return False
    return any(r.id == BYPASS_ROLE_ID for r in getattr(member, "roles", []))


def _clip(text, limit: int = 1024) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _code_block(text, limit: int = 1000) -> str:
    safe = str(text).replace("`", "'")[:limit]
    return f"```\n{safe}\n```"


STEAM_ID_RE = re.compile(r"(7656119\d{10})")


async def resolve_steam_id(raw: str) -> str | None:
    if not raw:
        return None
    text = str(raw).strip()
    m = STEAM_ID_RE.search(text)
    if m:
        return m.group(1)
    m = re.search(r"/id/([A-Za-z0-9_\-\.]+)", text)
    if not m:
        return None
    key = os.getenv("STEAM_API_KEY")
    if not key:
        return None
    data = await api._get_json("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
                               params={"key": key, "vanityurl": m.group(1)})
    resp = (data or {}).get("response") or {}
    if resp.get("success") == 1 and resp.get("steamid"):
        return str(resp["steamid"])
    return None


_link_last_use: dict = {}


def _link_cooldown_left(member) -> float:
    if member.guild_permissions.administrator:
        return 0.0
    if NO_COOLDOWN_ROLE_ID and any(r.id == NO_COOLDOWN_ROLE_ID for r in getattr(member, "roles", [])):
        return 0.0
    left = LINK_COOLDOWN_SECONDS - (time.time() - _link_last_use.get(member.id, 0.0))
    return left if left > 0 else 0.0


async def _after_link(i: discord.Interaction, sid: str):
    try:
        s1 = await sync_role_by_id(i.guild, i.user, sid)
        s2 = await sync_clan_role_by_id(i.guild, i.user, sid)
        await log_to_channel(i.client, f"🔗 /link - {s1}\n{s2}")
    except Exception as e:
        await log_error(i.client, "/link.sync", e)


def duplicate_steam_ids() -> dict:
    owners: dict = {}
    for did, sid in (links_store.read() or {}).items():
        owners.setdefault(str(sid), []).append(str(did))
    return {sid: acc for sid, acc in owners.items() if len(acc) > 1}


async def prune_votes(days: int = 30) -> int:
    cutoff = now_utc() - datetime.timedelta(days=days)

    def _prune(db):
        removed = 0
        for mid in list(db):
            entry = db.get(mid)
            if not isinstance(entry, dict):
                db.pop(mid, None)
                removed += 1
                continue
            closed_at = entry.get("closed_at")
            if not closed_at:
                continue
            try:
                when = datetime.datetime.fromisoformat(str(closed_at))
            except Exception:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            if when < cutoff:
                db.pop(mid, None)
                removed += 1
        return removed

    return await votes_store.update(_prune)


def is_user_blocked(discord_id: int):
    db = bans_store.read()
    entry = db.get(str(discord_id))
    if not isinstance(entry, dict):
        return False, ""
    reason = entry.get("reason") or ""
    suffix = f" Причина: {reason}" if reason and reason != "-" else ""

    if str(entry.get("type", "")).lower() == "perm":
        return True, "⛔ Вам **перманентно запрещено** подавать заявки." + suffix

    until_raw = entry.get("until")
    if not until_raw:
        return False, ""
    try:
        until = datetime.datetime.fromisoformat(str(until_raw))
    except Exception:
        return False, ""
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)

    now = now_utc()
    if now < until:
        h, m = divmod(int((until - now).total_seconds() // 60), 60)
        return True, f"🚫 Вам **запрещено** подавать заявки. Осталось **{h} ч. {m} мин.**" + suffix

    try:
        asyncio.get_running_loop().create_task(
            bans_store.update(lambda d: d.pop(str(discord_id), None)))
    except RuntimeError:
        pass
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

    cur = {r for r in member.roles if r.name in ROLE_NAMES}
    role_id = None if user.get("_not_found") else user.get("roleId")

    if role_id is not None and role_id not in ROLE_MAP:
        return (f"ℹ️ {member.display_name}: roleId={role_id} нет в ROLE_MAP — "
                f"роли не тронуты (добавь в ROLE_MAP_JSON)")

    if role_id is None or ROLE_MAP[role_id] is None:
        if cur:
            for r in cur:
                try:
                    await member.remove_roles(r)
                except discord.Forbidden:
                    pass
            return f"🔄 {member.display_name}: сняты"
        return f"ℹ️ {member.display_name}: без изменений"

    target_name = ROLE_MAP[role_id]
    target = resolve_managed_role(guild, target_name)
    if target is None:
        return f"⚠️ роль '{target_name}' не найдена (проверь ROLE_IDS_JSON)"

    if cur == {target}:
        return f"✅ {member.display_name}: уже '{target_name}'"

    for r in cur:
        if r != target:
            try:
                await member.remove_roles(r)
            except discord.Forbidden:
                pass
    if target in member.roles:
        return f"✅ {member.display_name}: уже '{target_name}'"
    try:
        await member.add_roles(target)
        return f"✅ {member.display_name}: '{target_name}'"
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

    clan = await api.player_clan(steam_id, user)
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
        keep = collect_thread_keep_ids(thread.guild)
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
def _get_votes(mid) -> dict:
    st = votes_store.read().get(str(mid))
    if not isinstance(st, dict):
        st = {}
    st.setdefault("accept", 0)
    st.setdefault("deny", 0)
    st.setdefault("voters", [])
    st.setdefault("accept_voters", [])
    st.setdefault("deny_voters", [])
    return st


async def _save_votes(mid, st):
    await votes_store.update(lambda d: d.update({str(mid): st}))


def render_application_view(mid: int):
    view = ApplicationManagement()
    view.update_labels(mid)
    return view


async def _vote(interaction, kind):
    await interaction.response.defer()
    if not user_can_review(interaction.user):
        await safe_send(interaction.followup, "❌ Нет прав.", ephemeral=True)
        return

    mid = interaction.message.id
    st = _get_votes(mid)
    if st.get("closed"):
        await safe_send(interaction.followup, "🔒 Заявка уже закрыта.", ephemeral=True)
        return

    uid = interaction.user.id
    already = uid in st["voters"]
    if already and not user_can_spam_vote(interaction.user):
        await safe_send(interaction.followup, "Вы уже голосовали.", ephemeral=True)
        return

    st[kind] = st.get(kind, 0) + 1
    if not already:
        st["voters"].append(uid)
        st["accept_voters" if kind == "accept" else "deny_voters"].append(uid)
    await _save_votes(mid, st)

    solo = user_can_decide_solo(interaction.user)
    needed = 1 if solo else VOTES_REQUIRED
    if len(st["accept_voters"]) >= needed:
        decision = "accept"
    elif len(st["deny_voters"]) >= needed:
        decision = "deny"
    else:
        decision = None

    if decision is None:
        try:
            await interaction.message.edit(view=render_application_view(mid))
        except Exception as e:
            log(f"⚠️ _vote: {e}")
        return

    st["closed"] = True
    st["result"] = decision
    st["closed_at"] = now_utc().isoformat()
    st["closed_by"] = uid
    await _save_votes(mid, st)

    status = "Принят" if decision == "accept" else "Отклонен"
    view = render_application_view(mid)
    for c in view.children:
        c.disabled = True
    embed = interaction.message.embeds[0] if interaction.message.embeds else None
    if embed is not None:
        embed.set_footer(text=f"cs2red • Заявки в клан • {status} • {_human_time()}")
    try:
        if embed is not None:
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.message.edit(view=view)
    except Exception as e:
        log(f"⚠️ _vote.close: {e}")

    tid = extract_discord_id_from_embed(embed) if embed is not None else 0
    member = interaction.guild.get_member(tid) if tid else None
    if decision == "accept" and member and AUTO_ROLE_ID:
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
            f"{'✅' if decision == 'accept' else '❌'} {member.mention} "
            f"(за: {len(st['accept_voters'])}, против: {len(st['deny_voters'])})")

    if embed is not None and APPS_LOG_CHANNEL_ID:
        try:
            log_channel = interaction.client.get_channel(APPS_LOG_CHANNEL_ID)
        except Exception:
            log_channel = None
        if log_channel is not None:
            if solo:
                note = (f"{'✅ Принята' if decision == 'accept' else '❌ Отклонена'} — "
                        f"{interaction.user.mention} (заместитель, единолично)")
            else:
                note = (f"{'✅ Принята' if decision == 'accept' else '❌ Отклонена'} — "
                        f"{interaction.user.mention} "
                        f"(голоса за/против: {len(st['accept_voters'])}/{len(st['deny_voters'])})")
            try:
                card = embed.copy()
                card.add_field(name="Решение", value=note, inline=False)
                card.set_footer(text=f"cs2red • Заявки в клан • "
                                     f"{'Принята' if decision == 'accept' else 'Отклонена'} • "
                                     f"{_human_time()}")
                await safe_send(log_channel, embed=card)
            except Exception as e:
                log(f"⚠️ карточка решения: {e}")
    if isinstance(interaction.channel, discord.Thread):
        await close_application_thread(interaction.channel, interaction.user, status)


# ============================================================
# МЕНЮ ЗАЯВКИ
# ============================================================
class ApplicationManagement(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def update_labels(self, mid):
        st = _get_votes(mid)
        accept = len(st.get("accept_voters") or [])
        deny = len(st.get("deny_voters") or [])
        closed = bool(st.get("closed"))
        for c in self.children:
            if c.custom_id == "accept_btn":
                c.label = (f"✅ Принять {accept}/{VOTES_REQUIRED}" if VOTES_REQUIRED > 1
                           else "✅ Принять")
                c.disabled = closed
            elif c.custom_id == "deny_btn":
                c.label = (f"❌ Отклонить {deny}/{VOTES_REQUIRED}" if VOTES_REQUIRED > 1
                           else "❌ Отклонить")
                c.disabled = closed
            elif c.custom_id == "voted_list_btn":
                c.label = f"👥 {len(st.get('voters') or [])}"

    @discord.ui.button(label="🙋 Взять", style=discord.ButtonStyle.primary,
                       custom_id="take_btn", row=0)
    async def take(self, i, b):
        await i.response.defer()
        if not user_can_review(i.user):
            await safe_send(i.followup, "❌", ephemeral=True)
            return
        await safe_send(i.followup, f"🙋 Взял {i.user.mention}.")
        try:
            view = render_application_view(i.message.id)
            for child in view.children:
                if child.custom_id == "take_btn":
                    child.disabled = True
            await i.message.edit(view=view)
        except Exception as e:
            log(f"⚠️ take: {e}")

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success,
                       custom_id="accept_btn", row=0)
    async def accept(self, i, b):
        await _vote(i, "accept")

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger,
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
        def _line(title, ids):
            if not ids:
                return f"**{title}:** —"
            return f"**{title}:** " + ", ".join(f"<@{u}>" for u in ids)
        await i.response.send_message(
            _line("За", st.get("accept_voters")) + "\n" + _line("Против", st.get("deny_voters")),
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
# КАРТОЧКА ЗАЯВКИ
# ============================================================
MSK = datetime.timezone(datetime.timedelta(hours=3))


def _human_time() -> str:
    now = now_utc().astimezone(MSK)
    return f"Сегодня, в {now.strftime('%H:%M')}"


def build_application_embed(nickname, steam_id=None, age="", discord_name="",
                            play_time="", comment="", avatar_url=None,
                            applicant_mention=None, status=None, decision_note=None):
    e = discord.Embed(title="Заявка в клан", color=APPLY_EMBED_COLOR)
    e.add_field(name="Игрок", value=_clip(nickname, 200), inline=False)

    if steam_id:
        e.add_field(name="Профиль Steam",
                    value=f"[перейти](https://steamcommunity.com/profiles/{steam_id})",
                    inline=False)
        e.add_field(name="Профиль на сайте",
                    value=f"[перейти](https://cs2red.ru/profile/{steam_id})", inline=False)
        e.add_field(name="Статистика",
                    value=f"[перейти](https://csstats.gg/player/{steam_id})", inline=False)
    else:
        e.add_field(name="Профиль Steam", value="не распознан", inline=False)

    e.add_field(name="Возраст", value=_code_block(age), inline=False)
    e.add_field(name="Discord для связи", value=_code_block(discord_name), inline=False)
    e.add_field(name="Время в которое удобно играть (по МСК)",
                value=_code_block(play_time), inline=False)
    if comment and str(comment).strip():
        e.add_field(name="Комментарий (не обязательно)",
                    value=_code_block(comment), inline=False)

    e.add_field(name="SteamID", value=f"`{steam_id}`" if steam_id else "`не распознан`",
                inline=False)
    if applicant_mention:
        e.add_field(name="Discord (упоминание)", value=applicant_mention, inline=False)
    if decision_note:
        e.add_field(name="Решение", value=decision_note, inline=False)

    if avatar_url:
        e.set_thumbnail(url=avatar_url)

    footer = "cs2red • Заявки в клан"
    if status:
        footer += f" • {status}"
    e.set_footer(text=f"{footer} • {_human_time()}")
    return e


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
        if not has_bypass_role(i.user):
            blocked, rt = is_user_blocked(i.user.id)
            if blocked:
                await safe_send(i.followup, rt, ephemeral=True)
                return
        sid = await resolve_steam_id(self.steam_input.value)
        e = build_application_embed(
            nickname=self.nickname.value,
            steam_id=sid,
            age=self.age.value,
            discord_name=i.user.name,
            play_time=self.time.value,
            comment=self.reason.value,
            avatar_url=i.user.display_avatar.url,
            applicant_mention=i.user.mention,
        )

        ch = i.guild.get_channel(APPLICATIONS_CHANNEL_ID) if APPLICATIONS_CHANNEL_ID else None
        if ch:
            try:
                msg = await safe_send(ch, content=f"🔔 Новая заявка от {i.user.mention}",
                                      embed=e, view=ApplicationManagement())
                if msg:
                    await msg.edit(view=render_application_view(msg.id))
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
        msg = await safe_send(t, content=f"{i.user.mention}, ваша заявка на рассмотрении.",
                              embed=e, view=ApplicationManagement())
        if msg:
            await msg.edit(view=render_application_view(msg.id))
    except Exception as ex:
        log(f"⚠️ Ветка: {ex}")


class ClanSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(custom_id="clan_select", placeholder="Выберите клан",
                         min_values=1, max_values=1,
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
PUBLIC_COMMANDS = {"link", "link_confirm", "unlink", "ping", "lookup", "rules", "ask", "ai_clear"}


async def _global_interaction_check(i: discord.Interaction) -> bool:
    cmd = getattr(i, "command", None)
    if cmd is None or cmd.name in PUBLIC_COMMANDS:
        return True
    if is_moderator(i.user.id, i.guild):
        return True
    try:
        if not i.response.is_done():
            await i.response.send_message("❌ Нет доступа.", ephemeral=True)
    except Exception as e:
        log(f"⚠️ interaction_check: {e}")
    return False


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

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

            self.tree.interaction_check = _global_interaction_check
            log("✅ Глобальная проверка доступа подключена")

            self.add_view(ClanView())
            log("✅ ClanView добавлен (заявки живут после рестарта)")

            self.add_view(ControlPanel())
            log("✅ ControlPanel добавлен (панель управления)")

            # auto_sync отключён — запускается вручную через /sync.
            # auto_sync.start()
            activity_tracker.start()
            dashboard_loop.start()

            if rules_base is not None:
                rules_refresher.start()
            if ai_client is not None and ai_client.enabled:
                ai_error_watcher.start()

            if github_sync is not None and github_sync.enabled:
                status = await pull_data_from_github()
                log(f"☁️ GitHub при старте: {status}")
                data_push_loop.start()

            log("✅ Все фоновые задачи запущены (auto_sync отключён)")
        except Exception as e:
            log(f"❌ ОШИБКА в setup_hook: {type(e).__name__}: {e}")
            traceback.print_exc()
            raise

    async def close(self):
        await api.close()
        await super().close()


bot = MyBot()


# ============================================================
# ПАНЕЛЬ УПРАВЛЕНИЯ
# ============================================================
class ControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def build_embed(self) -> discord.Embed:
        ws = bot.latency * 1000 if bot.is_ready() else 0
        up = int(time.time() - BOT_START_TIME)
        d, r = divmod(up, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        us = (f"{d} д. {h} ч." if d else
              f"{h} ч. {m} мин." if h else
              f"{m} мин. {s} сек." if m else f"{s} сек.")

        e = discord.Embed(
            title="🎛️ Панель управления Quantum",
            description="Управление ботом клана TALENT. Кнопки ниже.",
            color=AI_EMBED_COLOR,
            timestamp=now_utc(),
        )
        e.add_field(name="⏱ Аптайм", value=f"`{us}`", inline=True)
        e.add_field(name="📡 WS", value=f"`{ws:.0f} мс`", inline=True)
        e.add_field(name="🍪 Cookies", value=f"`{len(CS2RED_COOKIES)}`", inline=True)
        e.add_field(name="🔗 Привязок",
                    value=f"`{len(links_store.read())}`", inline=True)
        e.add_field(name="📁 Заявок",
                    value=f"`{len(votes_store.read())}`", inline=True)
        e.add_field(name="⚠️ Ошибок",
                    value=f"`{len(_error_ring)}`", inline=True)
        e.add_field(name="🤖 ИИ",
                    value=(ai_client.status_line()[:200] if ai_client else "выключен"),
                    inline=False)
        e.add_field(name="📚 Правила",
                    value=(rules_base.status_line()[:200] if rules_base else "нет модуля"),
                    inline=False)
        e.add_field(name="☁️ GitHub",
                    value=(github_sync.status_line()[:200] if github_sync else "не загружен"),
                    inline=False)
        e.set_footer(text=f"Quantum • {utc_stamp()}")
        if bot.user:
            e.set_thumbnail(url=bot.user.display_avatar.url)
        return e

    @discord.ui.button(label="🔗 Привязать всех", style=discord.ButtonStyle.success,
                       custom_id="panel_link_all", row=0)
    async def link_all_btn(self, i, b):
        if not is_moderator(i.user.id, i.guild):
            await i.response.send_message("❌ Нет доступа.", ephemeral=True)
            return

        log("🔗 Кнопка «Привязать всех» нажата")

        await i.response.defer(ephemeral=True)
        try:
            await safe_send(i.followup,
                f"⏳ Массовая привязка запущена. Задержка: {LINK_ALL_DELAY} сек. "
                f"Отчёт придёт в канал ручного разбора.",
                ephemeral=True)
        except Exception as e:
            log(f"⚠️ link_all: ephemeral: {e}")

        try:
            MANUAL_CHANNEL = UNLINKED_CHANNEL_ID
            links = links_store.read()
            guild = i.guild

            added = []
            already = []
            not_found = []
            multiple = []
            errors = []

            total = len([m for m in guild.members if not m.bot and str(m.id) not in links])
            done = 0

            for member in guild.members:
                if member.bot:
                    continue
                if str(member.id) in links:
                    already.append(member.display_name)
                    continue

                username = (member.name or "").strip()
                if not username:
                    continue

                try:
                    data = await api._get_json(
                        "https://cs2red.ru/api/admin/users",
                        params={"begin": 0, "count": 10, "search": username}
                    )
                except Exception as e:
                    errors.append(f"{member.display_name} (`{username}`): {e}")
                    await asyncio.sleep(LINK_ALL_DELAY)
                    continue

                if not data or not data.get("success"):
                    not_found.append(f"{member.display_name} (`{username}`)")
                    await asyncio.sleep(LINK_ALL_DELAY)
                    continue

                users = data.get("users") or []
                exact = [u for u in users
                         if str(u.get("nick", "")).lower() == username.lower()]
                if not exact:
                    exact = users

                if not exact:
                    not_found.append(f"{member.display_name} (`{username}`)")
                    await asyncio.sleep(LINK_ALL_DELAY)
                    continue

                if len(exact) > 1:
                    accs = ", ".join(
                        f"`{u.get('nick', '?')}` (`{u.get('steamid64', '?')}`)"
                        for u in exact[:5]
                    )
                    multiple.append(
                        f"{member.display_name} (`{username}`): {len(exact)} акк. → {accs}"
                    )
                    await asyncio.sleep(LINK_ALL_DELAY)
                    continue

                steamid = str(exact[0].get("steamid64") or "")
                if not steamid:
                    not_found.append(f"{member.display_name} (`{username}`) — нет SteamID")
                    await asyncio.sleep(LINK_ALL_DELAY)
                    continue

                try:
                    await links_store.update(lambda d: d.update({str(member.id): steamid}))
                except Exception as e:
                    errors.append(f"{member.display_name}: не сохранил — {e}")
                    await asyncio.sleep(LINK_ALL_DELAY)
                    continue

                added.append(
                    f"✅ {member.display_name} (`{username}`) → `{steamid}` "
                    f"({exact[0].get('nick', '?')})"
                )

                try:
                    await sync_role_by_id(guild, member, steamid)
                    await sync_clan_role_by_id(guild, member, steamid)
                except Exception as e:
                    log(f"⚠️ link_all: роли {member.display_name}: {e}")

                done += 1

                if done % 25 == 0:
                    try:
                        ch = bot.get_channel(MANUAL_CHANNEL)
                        if ch:
                            await safe_send(ch, f"⏳ Прогресс: обработано {done}/{total}…")
                    except Exception:
                        pass

                await asyncio.sleep(LINK_ALL_DELAY)

            if multiple or not_found or errors or added:
                lines = [f"📋 **Массовая привязка завершена** — {utc_stamp()}\n"]
                lines.append(f"✅ Привязано: **{len(added)}**")
                lines.append(f"ℹ️ Уже привязано: **{len(already)}**")
                lines.append(f"⚠️ Несколько аккаунтов: **{len(multiple)}**")
                lines.append(f"❓ Не найдено: **{len(not_found)}**")
                lines.append(f"🔴 Ошибок: **{len(errors)}**\n")

                if added:
                    lines.append("**Последние привязанные:**\n" + "\n".join(added[-10:]) + "\n")
                if multiple:
                    lines.append(f"⚠️ **Несколько аккаунтов** ({len(multiple)}):\n"
                                 + "\n".join(multiple[:20]) + "\n")
                if not_found:
                    lines.append(f"❓ **Не найдено на cs2red** ({len(not_found)}):\n"
                                 + "\n".join(not_found[:30]) + "\n")
                if errors:
                    lines.append(f"🔴 **Ошибки** ({len(errors)}):\n"
                                 + "\n".join(errors[:15]))

                text_manual = "\n".join(lines)

                try:
                    ch = bot.get_channel(MANUAL_CHANNEL)
                    if ch is None:
                        log(f"⚠️ link_all: канал {MANUAL_CHANNEL} не найден")
                    else:
                        for k in range(0, len(text_manual), 1900):
                            await safe_send(ch, text_manual[k:k + 1900])
                            await asyncio.sleep(1)
                except Exception as e:
                    log(f"⚠️ link_all: отчёт: {e}")

            try:
                await i.followup.send(
                    f"📊 Массовая привязка завершена: "
                    f"+{len(added)}, уже {len(already)}, мульти {len(multiple)}, "
                    f"не найдено {len(not_found)}, ошибок {len(errors)}. "
                    f"Подробный отчёт — в <#{MANUAL_CHANNEL}>",
                    ephemeral=True)
            except Exception as e:
                log(f"⚠️ link_all: финальный ephemeral: {e}")

            await ai_log(f"🔗 Массовая привязка: +{len(added)}, уже {len(already)}, "
                         f"мульти {len(multiple)}, не найдено {len(not_found)}, "
                         f"ошибок {len(errors)}")
        except Exception as e:
            await log_error(i.client, "link_all_btn", e)
            try:
                await i.followup.send(f"❌ Ошибка: {str(e)[:200]}", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="🔄 Синхронизация", style=discord.ButtonStyle.primary,
                       custom_id="panel_sync", row=0)
    async def sync_btn(self, i, b):
        if not is_moderator(i.user.id, i.guild):
            await i.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        log("🔄 Кнопка «Синхронизация» нажата")
        await i.response.defer(ephemeral=True)
        try:
            links = links_store.read()
            guild = i.guild
            dups = duplicate_steam_ids()
            count = 0
            for did, sid in dict(links).items():
                if api.auth_blocked():
                    break
                if str(sid) in dups:
                    continue
                m = guild.get_member(int(did))
                if m is None:
                    continue
                try:
                    await sync_role_by_id(guild, m, sid)
                    await sync_clan_role_by_id(guild, m, sid)
                    count += 1
                except Exception as e:
                    await log_error(i.client, f"panel.sync:{did}", e)
                await asyncio.sleep(SYNC_BTN_DELAY)
            await i.followup.send(f"✅ Синхронизировано: {count}", ephemeral=True)
        except Exception as e:
            await log_error(i.client, "panel.sync", e)
            await i.followup.send(f"❌ Ошибка: {str(e)[:200]}", ephemeral=True)

    @discord.ui.button(label="📚 Обновить правила", style=discord.ButtonStyle.primary,
                       custom_id="panel_rules", row=1)
    async def rules_btn(self, i, b):
        if not is_moderator(i.user.id, i.guild):
            await i.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        await i.response.defer(ephemeral=True)
        status = await refresh_rules_once()
        await ai_log(f"📚 Правила обновлены вручную: {status}")
        await i.followup.send(f"✅ {status}", ephemeral=True)

    @discord.ui.button(label="☁️ Выгрузить в GitHub", style=discord.ButtonStyle.primary,
                       custom_id="panel_github", row=1)
    async def github_btn(self, i, b):
        if not is_moderator(i.user.id, i.guild):
            await i.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        await i.response.defer(ephemeral=True)
        if github_sync is None or not github_sync.enabled:
            await i.followup.send("❌ GitHub не настроен.", ephemeral=True)
            return
        pushed, status = await github_sync.push(
            api.session or _NoSession(), GITHUB_SYNC_FILES, DATA_DIR)
        await i.followup.send(f"✅ {status}", ephemeral=True)

    @discord.ui.button(label="🩺 Health", style=discord.ButtonStyle.secondary,
                       custom_id="panel_health", row=2)
    async def health_btn(self, i, b):
        await i.response.defer(ephemeral=True)
        text = (f"**Аптайм:** {int(time.time() - BOT_START_TIME)} сек\n"
                f"**Cookies:** {len(CS2RED_COOKIES)}\n"
                f"**Привязок:** {len(links_store.read())}\n"
                f"**Заявок:** {len(votes_store.read())}\n"
                f"**Ошибок в буфере:** {len(_error_ring)}\n"
                f"**ИИ:** {ai_client.status_line() if ai_client else 'выкл'}\n"
                f"**Правила:** {rules_base.status_line() if rules_base else 'нет'}\n"
                f"**GitHub:** {github_sync.status_line() if github_sync else 'нет'}")
        await i.followup.send(text[:1900], ephemeral=True)

    @discord.ui.button(label="📊 Статус ИИ", style=discord.ButtonStyle.secondary,
                       custom_id="panel_ai", row=2)
    async def ai_btn(self, i, b):
        await i.response.defer(ephemeral=True)
        await i.followup.send(ai_status_text()[:1900], ephemeral=True)

    @discord.ui.button(label="🔄 Обновить панель", style=discord.ButtonStyle.secondary,
                       custom_id="panel_refresh", row=2)
    async def refresh_btn(self, i, b):
        await i.response.edit_message(embed=self.build_embed(), view=self)


@bot.tree.command(name="panel", description="Панель управления ботом (только для модераторов)")
async def panel_cmd(i: discord.Interaction):
    if not is_moderator(i.user.id, i.guild):
        await i.response.send_message("❌ Нет доступа.", ephemeral=True)
        return
    await i.response.defer(ephemeral=False)
    view = ControlPanel()
    await safe_send(i.followup, embed=view.build_embed(), view=view)


# ============================================================
# /sync — РУЧНАЯ СИНХРОНИЗАЦИЯ РОЛЕЙ
# ============================================================
@bot.tree.command(name="sync", description="Запустить синхронизацию ролей вручную (только для модераторов)")
async def sync_cmd(i: discord.Interaction):
    if not is_moderator(i.user.id, i.guild):
        await i.response.send_message("❌ Нет доступа.", ephemeral=True)
        return

    await i.response.defer(ephemeral=False)
    await safe_send(i.followup,
                    f"⏳ Синхронизация запущена. Задержка: {SYNC_CMD_DELAY} сек между игроками. "
                    f"Это может занять несколько минут…", ephemeral=False)

    try:
        links = links_store.read()
        guild = i.guild
        if not links or guild is None:
            await safe_send(i.followup, "ℹ️ Нет привязок для синхронизации.", ephemeral=False)
            return

        links_snapshot = dict(links)
        dups = duplicate_steam_ids()
        count = 0
        errors = 0
        total = len([x for x in links_snapshot if str(x[1]) not in dups])

        for did, sid in links_snapshot.items():
            if api.auth_blocked():
                await safe_send(i.followup,
                                "⚠️ Прервано: админка cs2red отдаёт 403. "
                                "Обнови `CS2RED_COOKIE_STRING` в Render.",
                                ephemeral=False)
                break
            if str(sid) in dups:
                continue
            m = guild.get_member(int(did))
            if m is None:
                continue
            try:
                await sync_role_by_id(guild, m, sid)
                await sync_clan_role_by_id(guild, m, sid)
                count += 1
            except Exception as e:
                errors += 1
                await log_error(i.client, f"sync_cmd:{did}", e)
            await asyncio.sleep(SYNC_CMD_DELAY)

        text = (f"✅ **Синхронизация завершена**\n"
                f"Обработано: **{count}**/{total}\n"
                f"Ошибок: **{errors}**\n"
                f"Пропущено дублей: **{len(dups)}**")
        await safe_send(i.followup, text, ephemeral=False)
        await ai_log(f"🔄 /sync: обработано {count}/{total}, ошибок {errors}, дублей {len(dups)}")
        await log_to_channel(i.client,
            f"🔄 /sync — обработано {count}/{total}, ошибок {errors}, дублей {len(dups)}")
    except Exception as e:
        await log_error(i.client, "/sync", e)
        await safe_send(i.followup, f"❌ Ошибка: {str(e)[:200]}", ephemeral=False)


@bot.tree.error
async def on_app_command_error(i, err):
    async def _reply(text: str):
        try:
            if not i.response.is_done():
                await i.response.send_message(text, ephemeral=True)
            else:
                await safe_send(i.followup, text, ephemeral=True)
        except Exception as e:
            log(f"⚠️ error-reply: {e}")

    if isinstance(err, app_commands.CommandOnCooldown):
        await _reply(f"⏱ Слишком часто. Подожди {err.retry_after:.0f} сек.")
        return
    if isinstance(err, app_commands.CheckFailure):
        await _reply("❌ Нет доступа.")
        return

    await log_error(i.client, f"cmd:{getattr(i.command, 'name', '?')}", err)
    await _reply("❌ Внутренняя ошибка. Подробности уже в логе бота.")


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
@app_commands.describe(steam_id="SteamID64 (17 цифр) или ссылка на профиль Steam")
async def link(i, steam_id: str):
    left = _link_cooldown_left(i.user)
    if left > 0:
        await i.response.send_message(f"⏱ Подожди {left:.0f} сек.", ephemeral=True)
        return

    sid = await resolve_steam_id(steam_id)
    if not sid:
        await i.response.send_message(
            "❌ Не понял SteamID. Пришли 17 цифр (`7656119…`) "
            "или ссылку на профиль Steam.", ephemeral=True)
        return

    await i.response.defer(ephemeral=False)
    try:
        existing = links_store.read()
        owner = next((d for d, s in existing.items() if s == sid), None)
        if owner and int(owner) != i.user.id:
            await safe_send(i.followup,
                "❌ Этот SteamID уже привязан к другому участнику. "
                "Если это ошибка — напиши администрации.", ephemeral=False)
            return
        if existing.get(str(i.user.id)) == sid:
            await safe_send(i.followup, f"ℹ️ Уже привязано: `{sid}`", ephemeral=False)
            return

        try:
            u = await asyncio.wait_for(api.cs2red_user(sid), timeout=CMD_API_TIMEOUT)
        except asyncio.TimeoutError:
            await safe_send(i.followup,
                "⚠️ cs2red не ответил за 30 сек. Попробуй позже или проверь `/health`.",
                ephemeral=False)
            return
        if u is None:
            await safe_send(i.followup,
                "⚠️ cs2red недоступен (сеть или 403). Проверь `/health`.", ephemeral=False)
            return
        if u.get("_not_found"):
            await safe_send(i.followup, f"❌ Игрок `{sid}` не найден на cs2red.", ephemeral=False)
            return

        if LINK_VERIFY and not is_moderator(i.user.id, i.guild):
            if not os.getenv("STEAM_API_KEY"):
                await safe_send(i.followup,
                    "❌ Проверка владения Steam недоступна: администратор не задал "
                    "`STEAM_API_KEY`. Обратись к администрации.", ephemeral=False)
                return
            code = f"QNTM-{random.randint(1000, 9999)}"
            await pending_store.update(lambda d: d.update({str(i.user.id): {
                "steam_id": sid, "code": code, "created": now_utc().isoformat()}}))
            _link_last_use[i.user.id] = time.time()
            await safe_send(i.followup,
                f"🔐 **Проверка владения аккаунтом**\n"
                f"1. Steam → профиль → «Изменить профиль».\n"
                f"2. Поставь **ник** ровно: `{code}`\n"
                f"3. Сохрани и вызови `/link_confirm` "
                f"(за {LINK_CODE_TTL_MINUTES} мин).\n"
                f"4. После проверки верни свой прежний ник.\n\n"
                f"Так мы убеждаемся, что аккаунт твой, а не чужой: "
                f"привязка даёт роли клана.", ephemeral=False)
            return

        await links_store.update(lambda d: d.update({str(i.user.id): sid}))
        _link_last_use[i.user.id] = time.time()
        await safe_send(i.followup,
            f"✅ Привязано: `{sid}` (ник **{u.get('nick', '-')}**)", ephemeral=False)
        await _after_link(i, sid)
    except Exception as e:
        await log_error(i.client, "/link", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="link_confirm", description="Подтвердить владение Steam-аккаунтом")
async def link_confirm(i):
    await i.response.defer(ephemeral=False)
    try:
        entry = pending_store.read().get(str(i.user.id))
        if not isinstance(entry, dict) or not entry.get("steam_id"):
            await safe_send(i.followup, "ℹ️ Нет активной проверки. Сначала `/link`.", ephemeral=True)
            return

        try:
            created = datetime.datetime.fromisoformat(str(entry.get("created")))
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
        except Exception:
            created = None
        if created and now_utc() - created > datetime.timedelta(minutes=LINK_CODE_TTL_MINUTES):
            await pending_store.update(lambda d: d.pop(str(i.user.id), None))
            await safe_send(i.followup, "⌛ Код устарел, начни заново: `/link`.", ephemeral=True)
            return

        sid = str(entry["steam_id"])
        code = str(entry["code"])

        try:
            summ = await asyncio.wait_for(api.steam_summary(sid), timeout=CMD_API_TIMEOUT)
        except asyncio.TimeoutError:
            await safe_send(i.followup, "⚠️ Steam не ответил за 30 сек. Попробуй позже.", ephemeral=True)
            return
        if summ is None:
            await safe_send(i.followup,
                "⚠️ Steam API недоступен. Попробуй позже.", ephemeral=True)
            return
        if not summ:
            await safe_send(i.followup,
                "❌ Профиль Steam не найден или закрыт. Проверь настройки приватности.",
                ephemeral=True)
            return

        nick = str(summ.get("personaname") or "").strip()
        if nick.casefold() != code.casefold():
            await safe_send(i.followup,
                f"❌ В нике Steam сейчас `{nick or '—'}`, а нужен ровно `{code}`. "
                f"Сохрани ник и вызови `/link_confirm` снова.", ephemeral=True)
            return

        existing = links_store.read()
        owner = next((d for d, s in existing.items() if s == sid), None)
        if owner and int(owner) != i.user.id:
            await safe_send(i.followup,
                "❌ Этот SteamID уже привязан к другому участнику.", ephemeral=True)
            return

        await links_store.update(lambda d: d.update({str(i.user.id): sid}))
        await pending_store.update(lambda d: d.pop(str(i.user.id), None))
        _link_last_use[i.user.id] = time.time()
        await safe_send(i.followup,
            f"✅ Аккаунт подтверждён и привязан: `{sid}`\n"
            f"Не забудь вернуть прежний ник в Steam.", ephemeral=False)
        await _after_link(i, sid)
    except Exception as e:
        await log_error(i.client, "/link_confirm", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


async def strip_managed_roles(member) -> list:
    managed_names = {n for n in ROLE_MAP.values() if n}
    managed_ids = set(CLAN_ROLE_MAP.values())
    removed = []
    for role in list(member.roles):
        if role.name in managed_names or role.id in managed_ids:
            try:
                await member.remove_roles(role)
                removed.append(role.name)
            except discord.Forbidden:
                pass
    return removed


@bot.tree.command(name="admlink", description="Привязать участника к SteamID вручную (модерация)")
@app_commands.describe(steam_id="SteamID64 (17 цифр) или ссылка на профиль Steam",
                       member="Участник Discord, которого привязываем")
async def admlink(i, steam_id: str, member: discord.Member):
    if not is_moderator(i.user.id, i.guild):
        await i.response.send_message("❌ Нет доступа. Команда только для модерации.", ephemeral=True)
        await ai_log(f"🚫 {i.user} пытался вызвать /admlink без прав")
        return

    await i.response.defer(ephemeral=False)
    try:
        sid = await resolve_steam_id(steam_id)
        if not sid:
            await safe_send(i.followup,
                "❌ Не понял SteamID. Нужны 17 цифр (`7656119…`) или ссылка на профиль.",
                ephemeral=False)
            return

        try:
            u = await asyncio.wait_for(api.cs2red_user(sid), timeout=CMD_API_TIMEOUT)
        except asyncio.TimeoutError:
            await safe_send(i.followup, "⚠️ cs2red не ответил за 30 сек. Попробуй позже.",
                            ephemeral=False)
            return
        if u is None:
            await safe_send(i.followup, "⚠️ cs2red недоступен, привязку не делаю (см. `/health`).",
                            ephemeral=False)
            return
        if u.get("_not_found"):
            await safe_send(i.followup,
                f"❌ Игрок `{sid}` не найден на cs2red — проверь SteamID.", ephemeral=False)
            return

        links = links_store.read()
        old_sid = links.get(str(member.id))
        prev_owner = next((d for d, s in links.items()
                           if s == sid and d != str(member.id)), None)

        notes = []
        if old_sid and old_sid != sid:
            notes.append(f"у участника было `{old_sid}` — заменено")
        if prev_owner:
            await links_store.update(lambda d: d.pop(str(prev_owner), None))
            notes.append(f"SteamID был привязан к <@{prev_owner}> — перенесён на {member.mention}")

        await links_store.update(lambda d: d.update({str(member.id): sid}))
        _link_last_use[member.id] = 0.0

        await safe_send(i.followup,
            f"✅ {member.mention} привязан к `{sid}` "
            f"(ник на cs2red: **{u.get('nick', '-')}**)"
            + ("\nℹ️ " + "; ".join(notes) if notes else ""),
            ephemeral=False)

        s1 = await sync_role_by_id(i.guild, member, sid)
        s2 = await sync_clan_role_by_id(i.guild, member, sid)
        await safe_send(i.followup, f"{s1}\n{s2}", ephemeral=False)

        if prev_owner:
            old_member = i.guild.get_member(int(prev_owner))
            if old_member:
                try:
                    os1 = await sync_role_by_id(i.guild, old_member, sid)
                    os2 = await sync_clan_role_by_id(i.guild, old_member, sid)
                    await safe_send(i.followup,
                        f"♻️ Прежний владелец <@{prev_owner}>: {os1}\n{os2}", ephemeral=False)
                except Exception as e:
                    await log_error(i.client, "/admlink.previous_owner", e)

        await log_to_channel(i.client,
            f"🛠️ /admlink: {i.user.mention} привязал {member.mention} к `{sid}` "
            f"(cs2red: {u.get('nick', '-')})")
        await ai_log(f"🛠️ /admlink: {i.user} → {member} = `{sid}` — {s1}; {s2}")
    except Exception as e:
        await log_error(i.client, "/admlink", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="admunlink", description="Отвязать участника от SteamID (модерация)")
@app_commands.describe(member="Участник Discord")
async def admunlink(i, member: discord.Member):
    if not is_moderator(i.user.id, i.guild):
        await i.response.send_message("❌ Нет доступа. Команда только для модерации.", ephemeral=True)
        await ai_log(f"🚫 {i.user} пытался вызвать /admunlink без прав")
        return
    await i.response.defer(ephemeral=False)
    try:
        rid = await links_store.update(lambda d: d.pop(str(member.id), None))
        if rid is None:
            await safe_send(i.followup, "ℹ️ Участник не привязан.", ephemeral=False)
            return
        removed = await strip_managed_roles(member)
        await safe_send(i.followup,
            f"✅ {member.mention} отвязан от `{rid}`. "
            f"Снято ролей: {', '.join(removed) if removed else 'нет'}",
            ephemeral=False)
        await log_to_channel(i.client, f"🛠️ /admunlink: {i.user.mention} → {member.mention} (`{rid}`)")
        await ai_log(f"🛠️ /admunlink: {i.user} отвязал {member} от `{rid}`")
    except Exception as e:
        await log_error(i.client, "/admunlink", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="unlink", description="Отвязать SteamID")
async def unlink(i):
    await i.response.defer(ephemeral=False)
    try:
        rid = await links_store.update(lambda d: d.pop(str(i.user.id), None))
        await pending_store.update(lambda d: d.pop(str(i.user.id), None))
        if rid is None:
            await safe_send(i.followup, "ℹ️ Не привязан.", ephemeral=False)
            return
        removed = await strip_managed_roles(i.user)
        await safe_send(i.followup,
            f"✅ Отвязано. Снято: {', '.join(removed) if removed else 'нет'}",
            ephemeral=False
        )
    except Exception as e:
        await log_error(i.client, "/unlink", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="sync_all", description="Синхронизировать всех (алиас /sync)")
async def sync_all(i):
    await sync_cmd.callback(i)


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
            tmp = data_path("mass_links.json")
            tmp = tmp.with_name(tmp.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(valid, f, ensure_ascii=False, indent=2)
            os.replace(tmp, data_path("mass_links.json"))
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
        try:
            u = await asyncio.wait_for(api.cs2red_user(sid), timeout=CMD_API_TIMEOUT)
        except asyncio.TimeoutError:
            await safe_send(i.followup, "⚠️ cs2red не ответил за 30 сек.", ephemeral=False)
            return
        if u is None:
            await safe_send(i.followup, "⚠️ cs2red недоступен. Проверь `/health`.", ephemeral=False)
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
def build_ping_embed() -> discord.Embed:
    ws = bot.latency * 1000 if bot.is_ready() else 0
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
    e.add_field(name="🤖 ИИ",
                value=ai_client.status_line() if ai_client
                else "не настроен (нужен GEMINI_API_KEY)", inline=False)
    e.add_field(name="📚 Правила",
                value=rules_base.status_line() if rules_base else "модуль ai_rules не загружен",
                inline=False)
    e.add_field(name="☁️ GitHub-хранилище",
                value=github_sync.status_line() if github_sync else "модуль github_sync не загружен",
                inline=False)
    recent = [x for x in _error_ring if time.time() - x["ts"] < 3600]
    e.add_field(name="⚠️ Ошибки за час", value=f"`{len(recent)}`", inline=True)
    e.add_field(name="🍪 Cookies", value=f"`{len(CS2RED_COOKIES)}`", inline=True)
    e.add_field(name="🆔 Guild", value=f"`{GUILD_ID}`", inline=True)
    e.add_field(name="Python",
                value=f"{platform.python_version()} • discord.py {discord.__version__}",
                inline=False)
    e.set_footer(text=f"Quantum • {utc_stamp()}")
    if bot.user:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    return e


@bot.tree.command(name="ping", description="Проверить, жив ли бот и ИИ")
async def ping(i):
    await i.response.defer(ephemeral=False)
    await safe_send(i.followup, embed=build_ping_embed(), ephemeral=False)


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

    ws_ms = bot.latency * 1000 if bot.is_ready() else 0
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
                                   params={"begin": 0, "count": 1}, force=True)
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
        ("activity_tracker", activity_tracker, f"{ACTIVITY_TRACK_SECONDS // 60} мин"),
        ("dashboard_loop", dashboard_loop, f"{DASHBOARD_INTERVAL_MINUTES} мин"),
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

    add("⚙️", "Задача `auto_sync`",
        "❌ отключена (запуск вручную через `/sync`)", True)

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

    if ai_client is not None:
        add("🤖", "ИИ (Gemini/LLM)", ai_client.status_line(),
            bool(ai_client.enabled) and not ai_client.last_error)
        if api.auth_blocked():
            left = int(api._auth_block_until - time.time())
            add("⏸", "Запросы к админке cs2red",
                f"на паузе ещё {left // 60} мин. {left % 60} сек. "
                f"(были 403 — обнови CS2RED_*)", False)
    else:
        add("🤖", "ИИ (Gemini/LLM)",
            "выключен: нужен GEMINI_API_KEY или LLM7_API_KEY", False)

    if rules_base is not None and rules_base.size > 0:
        add("📚", "База правил", rules_base.status_line(), True)
    elif rules_base is not None and rules_base.ready:
        add("📚", "База правил",
            f"{rules_base.status_line()} — ни одного пункта не распознано, "
            f"ответы по правилам будут неточными. Положи rules.txt "
            f"(шаблон — rules.example.txt) в репозиторий данных", False)
    else:
        add("📚", "База правил",
            "нет данных — положи rules.txt в папку данных или задай RULES_API_URL", False)

    if github_sync is not None and github_sync.enabled:
        add("☁️", "GitHub-хранилище", github_sync.status_line(), not github_sync.last_error)
    else:
        add("☁️", "Хранение данных",
            "Persistent Disk (DATA_DIR=/data) или GITHUB_TOKEN+GITHUB_REPO", True)

    try:
        dups = duplicate_steam_ids()
        if dups:
            sample = ", ".join(f"`{s}` ×{len(o)}" for s, o in list(dups.items())[:5])
            add("🧬", "Дубли SteamID (роли не синхронизируются)",
                f"{sample}{' …' if len(dups) > 5 else ''}", False)
        else:
            add("🧬", "Дубли SteamID", "нет", True)
    except Exception as e:
        add("🧬", "Дубли SteamID", f"❌ {e}", False)

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
# ИИ-КОМАНДЫ (с контекстом диалога)
# ============================================================
def _ai_cooldown_left(user_id: int) -> float:
    left = AI_ASK_COOLDOWN_SECONDS - (time.time() - _ai_ask_last.get(user_id, 0.0))
    return left if left > 0 else 0.0


def _ai_context_add(channel_id: int, role: str, content: str):
    if channel_id not in _ai_context:
        _ai_context[channel_id] = deque(maxlen=_AI_CONTEXT_MAX * 2)
    _ai_context[channel_id].append({"role": role, "content": content[:500]})


def _ai_context_get(channel_id: int) -> list:
    if channel_id not in _ai_context:
        return []
    return list(_ai_context[channel_id])


def _ai_context_clear(channel_id: int):
    _ai_context.pop(channel_id, None)


def _no_rules_hint() -> str:
    return ("⚠️ База правил пока пуста. Администратору: положи `rules.txt` в папку данных "
            "(на Render — `/data`) или задай `RULES_API_URL`.")


def _fmt_clauses(matches, limit: int = 3, size: int = 700) -> str:
    lines = []
    for cid, body, _score in matches[:limit]:
        lines.append(f"📕 **Пункт {cid}**\n{body[:size]}")
    return "\n\n".join(lines)


async def answer_rules(question: str) -> tuple:
    if rules_base is None:
        return (f"⚠️ Модуль `ai_rules.py` не загружен ({_AI_IMPORT_ERROR}).", "нет модуля ai_rules")
    if not rules_base.ready:
        return (_no_rules_hint(), "запрос правил без базы")

    found = rules_base.lookup(question)
    if found["exact"]:
        cid, body = found["exact"]
        return (f"📕 **Пункт {cid}**\n{body[:1500]}", f"пункт {cid} найден по базе (без ИИ)")

    if ai_client is None or not ai_client.enabled:
        if found["matches"]:
            return ("ИИ выключен, вот что нашлось по словам:\n\n" + _fmt_clauses(found["matches"]),
                    "поиск по словам, ИИ выключен")
        return ("📕 Точного пункта в правилах не нашёл. Укажи номер, например `2.2`, "
                "или переформулируй вопрос.", "совпадений нет, ИИ выключен")

    context = rules_base.context_for(question)
    prompt = ai_rules.build_rules_prompt(question, context, rules_base.clause_ids())
    text, meta = await ai_client.ask(api.session, prompt, system=ai_rules.RULES_SYSTEM)
    if text:
        return (f"🤖 {text[:1800]}", f"ответ ИИ за {meta['latency']:.1f} с")
    if found["matches"]:
        return ("ИИ недоступен, вот ближайшие пункты по словам:\n\n"
                + _fmt_clauses(found["matches"]), f"ИИ недоступен: {meta['error']}")
    return (f"⚠️ ИИ недоступен: {meta['error'][:200]}", f"ИИ недоступен: {meta['error']}")


async def answer_general(question: str, channel_id: int = 0) -> tuple:
    """Свободный вопрос к ИИ с контекстом диалога."""
    if ai_client is None or not ai_client.enabled:
        return ("⚠️ ИИ не настроен: администратору нужно добавить `GEMINI_API_KEY`.",
                "ИИ выключен")

    context = rules_base.context_for(question, limit=4) if (rules_base and rules_base.ready) else ""
    history = _ai_context_get(channel_id) if channel_id else []

    history_text = ""
    if history:
        history_text = "\n\nПРЕДЫДУЩИЙ ДИАЛОГ:\n"
        for msg in history:
            role = "Игрок" if msg["role"] == "user" else "Ты"
            history_text += f"{role}: {msg['content']}\n"

    prompt = (f"КОНТЕКСТ (правила проекта cs2red.ru, может быть не по теме):\n{context}\n"
              f"{history_text}\n"
              f"ВОПРОС: {question}\n\n"
              f"Ответь кратко. Если вопрос про правила — ссылайся на номера пунктов, "
              f"если нет — просто помоги по существу.")

    text, meta = await ai_client.ask(api.session, prompt, system=ai_rules.ASK_SYSTEM)

    if channel_id:
        _ai_context_add(channel_id, "user", question)
        if text:
            _ai_context_add(channel_id, "assistant", text)

    if text:
        return (f"🤖 {text[:1800]}", f"ответ ИИ за {meta['latency']:.1f} с")
    return (f"⚠️ ИИ недоступен: {meta['error'][:200]}", f"ошибка ИИ: {meta['error']}")


def ai_status_text() -> str:
    lines = ["🤖 **Состояние ИИ**"]
    lines.append(f"• клиент: {ai_client.status_line() if ai_client else 'выключен'}")
    lines.append(f"• правила: {rules_base.status_line() if rules_base else 'нет модуля ai_rules'}")
    if _AI_IMPORT_ERROR:
        lines.append(f"• ошибка загрузки модуля: `{_AI_IMPORT_ERROR}`")
    lines.append(f"• канал логов ИИ: <#{AI_LOG_CHANNEL_ID}>" if AI_LOG_CHANNEL_ID
                 else "• канал логов ИИ: не задан")
    lines.append(f"• хранилище данных: "
                 f"{github_sync.status_line() if github_sync else 'модуль github_sync не загружен'}")
    lines.append(f"• DATA_DIR: `{DATA_DIR}`")
    lines.append(f"• контекст диалогов: каналов `{len(_ai_context)}`")
    if rules_base is not None and rules_base.size == 0:
        lines.append("• ⚠️ пунктов правил не найдено — положи `rules.txt` "
                     "в репозиторий данных и выполни `!ai_scan`")
    lines.append(f"• разбор ошибок: {'включён' if AI_ERROR_ANALYSIS else 'выключен'}, "
                 f"каждые {AI_ERROR_INTERVAL_MINUTES} мин")
    lines.append(f"• ошибок в буфере: `{len(_error_ring)}`")
    tail = list(_error_ring)[-5:]
    if tail:
        lines.append("• последние:")
        lines.extend(f"   `{e['time']}` {e['context']}: {e['error'][:110]}" for e in tail)
    else:
        lines.append("• последних ошибок нет")
    return "\n".join(lines)


@bot.tree.command(name="rules", description="Спросить про правила cs2red (номер пункта или вопрос)")
@app_commands.describe(question="Например: 2.2 или «что будет за баги карты»")
async def rules_cmd(i, question: str):
    left = _ai_cooldown_left(i.user.id)
    if left > 0:
        await i.response.send_message(f"⏱ Подожди {left:.0f} сек.", ephemeral=True)
        return
    await i.response.defer(ephemeral=False)
    _ai_ask_last[i.user.id] = time.time()
    try:
        answer, logline = await answer_rules(question)
        await safe_send(i.followup, answer, ephemeral=False)
        await ai_log(f"📕 /rules «{question[:120]}» — {i.user} → {logline}")
    except Exception as e:
        await log_error(i.client, "/rules", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="ask", description="Задать вопрос ИИ-помощнику (с контекстом диалога)")
@app_commands.describe(question="Любой вопрос по игре, клану или боту")
async def ask_cmd(i, question: str):
    left = _ai_cooldown_left(i.user.id)
    if left > 0:
        await i.response.send_message(f"⏱ Подожди {left:.0f} сек.", ephemeral=True)
        return
    await i.response.defer(ephemeral=False)
    _ai_ask_last[i.user.id] = time.time()
    try:
        answer, logline = await answer_general(question, channel_id=i.channel_id)
        await safe_send(i.followup, answer, ephemeral=False)
        await ai_log(f"💬 /ask «{question[:120]}» — {i.user} → {logline}")
    except Exception as e:
        await log_error(i.client, "/ask", e)
        await close_interaction(i, f"❌ Ошибка: {str(e)[:200]}")


@bot.tree.command(name="ai_status", description="Состояние ИИ, правил и последние ошибки")
async def ai_status_cmd(i):
    await i.response.defer(ephemeral=False)
    await safe_send(i.followup, ai_status_text(), ephemeral=False)


@bot.tree.command(name="ai_clear", description="Очистить контекст диалога с ИИ в этом канале")
async def ai_clear_cmd(i: discord.Interaction):
    _ai_context_clear(i.channel_id)
    await i.response.send_message("✅ Контекст диалога очищен. ИИ больше не помнит "
                                  "предыдущие сообщения в этом канале.", ephemeral=True)


# ---------- префиксные версии ----------
@bot.command(name="ping")
async def ping_prefix(ctx):
    await safe_send(ctx.channel, embed=build_ping_embed())


@bot.command(name="rules")
async def rules_prefix(ctx, *, question: str = ""):
    if not question.strip():
        await safe_send(ctx.channel, "Использование: `!rules 2.2` или `!rules что будет за читы`")
        return
    left = _ai_cooldown_left(ctx.author.id)
    if left > 0:
        await safe_send(ctx.channel, f"⏱ {ctx.author.mention}, подожди {left:.0f} сек.")
        return
    _ai_ask_last[ctx.author.id] = time.time()
    try:
        answer, logline = await answer_rules(question)
        await safe_send(ctx.channel, answer)
        await ai_log(f"📕 !rules «{question[:120]}» — {ctx.author} → {logline}")
    except Exception as e:
        await log_error(ctx.bot, "!rules", e)
        await safe_send(ctx.channel, f"❌ Ошибка: {str(e)[:200]}")


@bot.command(name="ask")
async def ask_prefix(ctx, *, question: str = ""):
    if not question.strip():
        await safe_send(ctx.channel, "Использование: `!ask как вступить в клан?`")
        return
    left = _ai_cooldown_left(ctx.author.id)
    if left > 0:
        await safe_send(ctx.channel, f"⏱ {ctx.author.mention}, подожди {left:.0f} сек.")
        return
    _ai_ask_last[ctx.author.id] = time.time()
    try:
        answer, logline = await answer_general(question, channel_id=ctx.channel.id)
        await safe_send(ctx.channel, answer)
        await ai_log(f"💬 !ask «{question[:120]}» — {ctx.author} → {logline}")
    except Exception as e:
        await log_error(ctx.bot, "!ask", e)
        await safe_send(ctx.channel, f"❌ Ошибка: {str(e)[:200]}")


@bot.command(name="ai_status")
async def ai_status_prefix(ctx):
    if not is_moderator(ctx.author.id, ctx.guild):
        await safe_send(ctx.channel, "❌ Нет доступа.")
        return
    await safe_send(ctx.channel, ai_status_text())


@bot.tree.command(name="rules_probe", description="Диагностика: где бот ищет правила")
async def rules_probe_cmd(i):
    if not is_moderator(i.user.id, i.guild):
        await i.response.send_message("❌ Нет доступа.", ephemeral=True)
        return
    await i.response.defer(ephemeral=False)
    if rules_base is None:
        await safe_send(i.followup, f"❌ Модуль ai_rules не загружен: {_AI_IMPORT_ERROR}",
                        ephemeral=False)
        return
    try:
        lines = await rules_base.probe(api.session or _NoSession())
    except Exception as e:
        await log_error(i.client, "/rules_probe", e)
        await close_interaction(i, f"❌ Ошибка диагностики: {str(e)[:200]}")
        return
    text = "\n".join(lines)
    await ai_log("🔎 Диагностика правил:\n```\n" + text[:1800] + "\n```")
    await safe_send(i.followup,
        f"✅ Отчёт отправлен в <#{AI_LOG_CHANNEL_ID}>.\n"
        f"Найдено пунктов: **{rules_base.size}**, источник: {rules_base.source}",
        ephemeral=False)


@bot.command(name="ai_scan")
async def ai_scan_prefix(ctx):
    if not is_moderator(ctx.author.id, ctx.guild):
        await safe_send(ctx.channel, "❌ Нет доступа.")
        return
    await safe_send(ctx.channel, "⏳ Обновляю правила и разбираю ошибки…")
    status = await refresh_rules_once()
    await ai_log(f"📚 Правила обновлены вручную ({ctx.author}): {status}")
    report = await analyze_errors_once()
    if report:
        await _send_ai_report(report)
        await safe_send(ctx.channel, "✅ Готово, отчёт в канале логов ИИ.")
    else:
        await safe_send(ctx.channel, "✅ Новых ошибок для разбора нет.")


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

    old_id = setup_store.read().get(str(ctx.channel.id))
    if old_id:
        try:
            msg = await ctx.channel.fetch_message(int(old_id))
            await msg.edit(embed=e, view=v)
            await ctx.send("✅ Сообщение с заявками обновлено.", delete_after=10)
            return
        except Exception as e:
            log(f"⚠️ !setup: не обновил прежнее сообщение: {e}")

    msg = await safe_send(ctx.channel, embed=e, view=v)
    if msg:
        await setup_store.update(lambda d: d.update({str(ctx.channel.id): msg.id}))


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
        if not seen.get("_seeded"):
            for sid in links.values():
                if sid in n2s:
                    continue
                u = await api.cs2red_user(sid)
                if u and u.get("nick"):
                    n2s[u["nick"]] = sid
                    db.setdefault(sid, {})["cs2red_nick"] = u["nick"]
            await players_store.save(db)
            seen["_seeded"] = True
        for nick in list(seen):
            if nick != "_seeded" and nick not in online:
                seen.pop(nick, None)
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
# ДАШБОРД В КАНАЛЕ DB_CHANNEL_ID
# ============================================================
_dashboard_message_id: int = 0


async def build_dashboard_embed() -> discord.Embed:
    ws = bot.latency * 1000 if bot.is_ready() else 0
    up = int(time.time() - BOT_START_TIME)
    days, rem = divmod(up, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    uptime = (f"{days}д {hours}ч {mins}м" if days
              else (f"{hours}ч {mins}м" if hours else f"{mins}м"))

    links = links_store.read()
    total_links = len(links)

    db = players_store.read()
    active_players = sorted(
        ((sid, p) for sid, p in db.items() if p.get("activity")),
        key=lambda x: sum(float(v) for v in (x[1].get("activity") or {}).values()
                          if isinstance(v, (int, float))),
        reverse=True
    )[:10]

    top_lines = []
    for sid, p in active_players:
        nick = p.get("cs2red_nick") or p.get("discord_name") or sid
        hours = sum(float(v) for v in (p.get("activity") or {}).values()
                    if isinstance(v, (int, float)))
        bar = "█" * min(10, int(hours / 2))
        top_lines.append(f"`{str(nick)[:20]:20}` {bar} {hours:.1f} ч.")

    try:
        online = await api.server_times()
        online_count = len(online)
    except Exception:
        online_count = 0

    e = discord.Embed(
        title="📈 Дашборд Quantum — Активность",
        description=f"**Обновлено:** {utc_stamp()}",
        color=AI_EMBED_COLOR,
        timestamp=now_utc(),
    )
    e.add_field(name="⏱ Аптайм", value=f"`{uptime}`", inline=True)
    e.add_field(name="📡 WS", value=f"`{ws:.0f} мс`", inline=True)
    e.add_field(name="🔗 Привязок", value=f"`{total_links}`", inline=True)
    e.add_field(name="🌐 Онлайн сервера", value=f"`{online_count}` игроков", inline=True)
    e.add_field(name="📁 Заявок", value=f"`{len(votes_store.read())}`", inline=True)
    e.add_field(name="⚠️ Ошибок", value=f"`{len(_error_ring)}`", inline=True)

    if top_lines:
        e.add_field(
            name="🏆 Топ-10 активных за неделю",
            value="\n".join(top_lines) if top_lines else "—",
            inline=False,
        )

    e.add_field(
        name="🤖 ИИ",
        value=(ai_client.status_line()[:200] if ai_client else "выключен"),
        inline=False,
    )
    e.add_field(
        name="📚 Правила",
        value=(rules_base.status_line()[:200] if rules_base else "нет модуля"),
        inline=False,
    )

    if bot.user:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    e.set_footer(text=f"Quantum • Автообновление раз в {DASHBOARD_INTERVAL_MINUTES} мин")
    return e


@tasks.loop(minutes=DASHBOARD_INTERVAL_MINUTES)
async def dashboard_loop():
    global _dashboard_message_id
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if channel is None:
            log(f"⚠️ dashboard: канал {DASHBOARD_CHANNEL_ID} не найден")
            return

        embed = await build_dashboard_embed()

        if _dashboard_message_id:
            try:
                msg = await channel.fetch_message(_dashboard_message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                _dashboard_message_id = 0
            except Exception as e:
                log(f"⚠️ dashboard: не отредактировал: {e}")

        msg = await safe_send(channel, embed=embed)
        if msg:
            _dashboard_message_id = msg.id
    except Exception as e:
        await log_error(bot, "dashboard_loop", e)


@dashboard_loop.before_loop
async def before_dashboard_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(15)


# ============================================================
# ИИ: ОБНОВЛЕНИЕ ПРАВИЛ И РАЗБОР ОШИБОК
# ============================================================
class _NoSession:
    def get(self, *args, **kwargs):
        raise RuntimeError("HTTP-сессия ещё не создана")


async def refresh_rules_once() -> str:
    if rules_base is None:
        return f"модуль ai_rules не загружен: {_AI_IMPORT_ERROR}"
    try:
        count, status = await rules_base.refresh(api.session or _NoSession())
        return status
    except Exception as e:
        await log_error(bot, "refresh_rules_once", e)
        return f"ошибка обновления: {e}"


@tasks.loop(hours=RULES_TTL_HOURS)
async def rules_refresher():
    if rules_base is None:
        return
    before = (rules_base.source, rules_base.size)
    status = await refresh_rules_once()
    after = (rules_base.source, rules_base.size)
    if after[1] > 0 and after != before:
        await ai_log(f"📚 Правила обновлены: {status}")
    else:
        log(f"📚 Правила: {status}")


@rules_refresher.before_loop
async def before_rules_refresher():
    await bot.wait_until_ready()
    await asyncio.sleep(5)


def _bot_diagnostics() -> str:
    lines = [f"аптайм {int(time.time() - BOT_START_TIME)} c, "
             f"WS {(bot.latency * 1000 if bot.is_ready() else 0):.0f} мс"]
    for name, task_obj in (("activity_tracker", activity_tracker),
                           ("dashboard_loop", dashboard_loop),
                           ("rules_refresher", rules_refresher)):
        try:
            lines.append(f"задача {name}: {'работает' if task_obj.is_running() else 'ОСТАНОВЛЕНА'}")
        except Exception as e:
            lines.append(f"задача {name}: нет данных ({e})")
    lines.append("задача auto_sync: ОТКЛЮЧЕНА (запуск через /sync)")
    for name, store in (("links", links_store), ("players", players_store),
                        ("bans", bans_store), ("votes", votes_store)):
        try:
            data = store.read()
            lines.append(f"{name}: записей {len(data)}")
        except Exception as e:
            lines.append(f"{name}: ошибка чтения {e}")
    try:
        lines.append(f"дубли SteamID: {len(duplicate_steam_ids())}")
    except Exception as e:
        lines.append(f"дубли SteamID: ошибка {e}")
    lines.append(f"последний HTTP cs2red: {getattr(api, 'last_status', None)}")
    lines.append(f"правила: {rules_base.status_line() if rules_base else 'нет модуля'}")
    lines.append(f"ИИ: {ai_client.status_line() if ai_client else 'выключен'}")
    return "\n".join(lines)


async def analyze_errors_once() -> str:
    global _ai_last_error_report
    if ai_client is None or not ai_client.enabled:
        return "ИИ выключен"
    fresh = [e for e in list(_error_ring) if e["ts"] > _ai_last_error_report]
    if not fresh:
        return ""
    _ai_last_error_report = max(e["ts"] for e in fresh)
    prompt = ai_rules.build_error_prompt(fresh, _bot_diagnostics())
    text, meta = await ai_client.ask(api.session, prompt, system=ai_rules.SRE_SYSTEM,
                                     max_output_tokens=1200)
    if text:
        return ("EMBED", text, f"Ошибок: {len(fresh)} • {meta['latency']:.1f} с • "
                               f"модель {ai_client.model} • {_bot_stats_line()}")
    return ("TEXT", f"⚠️ ИИ не разобрал ошибки ({meta['error'][:200]}). "
                    f"Ошибок в пачке: {len(fresh)}", "")


async def _send_ai_report(report):
    if not report:
        return
    if isinstance(report, tuple):
        kind, body, footer = report
        if kind == "EMBED":
            await ai_log_embed("🤖 ИИ-анализ бота", body, footer)
            return
        await ai_log(body)
        return
    await ai_log(str(report)[:1900])


@tasks.loop(minutes=AI_ERROR_INTERVAL_MINUTES)
async def ai_error_watcher():
    if not AI_ERROR_ANALYSIS:
        return
    try:
        await _send_ai_report(await analyze_errors_once())
    except Exception as e:
        await log_error(bot, "ai_error_watcher", e)


@ai_error_watcher.before_loop
async def before_ai_error_watcher():
    await bot.wait_until_ready()
    await asyncio.sleep(60)


_gh_log_last = 0.0
_gh_log_saved = 0


@tasks.loop(seconds=GITHUB_PUSH_INTERVAL_SECONDS)
async def data_push_loop():
    global _gh_log_last, _gh_log_saved
    if github_sync is None or not github_sync.enabled or not _data_dirty:
        return

    allowed = set(GITHUB_SYNC_FILES)
    files = sorted(_data_dirty & allowed)
    _data_dirty.clear()
    if not files:
        return

    try:
        pushed, status = await github_sync.push(api.session or _NoSession(), files, DATA_DIR)
    except Exception as e:
        await log_error(bot, "data_push_loop", e)
        _data_dirty.update(files)
        return

    log(f"☁️ GitHub: {status}")
    _gh_log_saved += pushed

    failed = "не удалось" in status
    now = time.time()
    if not failed and _gh_log_last and now - _gh_log_last < GITHUB_LOG_INTERVAL_SECONDS:
        return

    _gh_log_last = now
    if _gh_log_saved or failed:
        msg = f"☁️ GitHub: сохранено файлов {_gh_log_saved}" if _gh_log_saved else "☁️ GitHub"
        if failed:
            msg += f"; {status}"
        await ai_log(msg)
    _gh_log_saved = 0


@data_push_loop.before_loop
async def before_data_push_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(30)


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
        log("❌ DISCORD_TOKEN не задан! Добавь его в переменные окружения.")
        sys.exit(1)
    if GUILD_ID == 0:
        log("❌ GUILD_ID не задан! Добавь его в переменные окружения.")
        sys.exit(1)
    threading.Thread(target=run_health_server, daemon=True).start()
    bot.run(DISCORD_TOKEN)
