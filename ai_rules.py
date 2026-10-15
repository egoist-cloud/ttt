# -*- coding: utf-8 -*-
"""
ИИ-помощник бота Quantum: Gemini Interactions API + база правил cs2red.ru.

Модуль ничего не знает про discord.py: логика отделена, чтобы её можно было
тестировать без Discord. Логи отдаются наружу через колбэк on_log.

Что внутри:
  * parse_clauses()      — находит пункты вида «2.2. Запрещено ...» в тексте;
  * html_to_text()       — HTML -> текст без внешних зависимостей;
  * js_to_text()         — разэкранирование JS-строк (правила сайта лежат в бандле);
  * RulesBase            — база правил: локальный файл, API, страница, JS-бандлы + кэш;
  * GeminiClient         — вызов POST /v1beta/interactions и разбор ответа.

Формат запроса и ответа сверен с официальной спецификацией:
https://ai.google.dev/api/interactions
ответ: {"status": "...", "steps": [{"type": "model_output",
                                   "content": [{"type": "text", "text": "..."}]}], "usage": {...}}
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import aiohttp

DEFAULT_RULES_URL = "https://cs2red.ru/rules"
DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.8-flash"

# Минимум пунктов, чтобы считать найденный текст правилами, а не мусором.
MIN_CLAUSES = 5

# По этим словам отбираем API-пути, похожие на правила или текстовые страницы.
API_HINTS = ("rule", "page", "content", "text", "info", "static", "document", "article")
MAX_FETCH_BYTES = 4_000_000


# ============================================================
# РАЗБОР ТЕКСТА
# ============================================================
class _TextExtractor(HTMLParser):
    """HTML -> текст. Заменяет bs4, чтобы не тянуть лишнюю зависимость."""

    SKIP = {"script", "style", "noscript", "svg"}
    BREAK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "td", "th", "ul", "ol", "table", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BREAK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BREAK:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth and data:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # битый HTML не должен ронять обновление правил
        return re.sub(r"<[^>]+>", " ", html)
    return normalize_text(parser.text())


def js_to_text(js: str) -> str:
    """Разэкранирует JS/JSON-строки: правила SPA лежат внутри бандла."""
    if not js:
        return ""
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), js)
    text = text.replace("\\n", "\n").replace("\\r", "\n").replace("\\t", " ")
    text = text.replace('\\"', '"').replace("\\'", "'").replace("\\/", "/")
    return normalize_text(text)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # markdown-мусор, который мешает распознать номер пункта
    text = re.sub(r"[*_`#>]+", " ", text)
    return text.strip()


# «2.2.», «2.2)», «2.2 -», «2.2:», «п. 2.2», «Пункт 2.2.»
CLAUSE_LINE_RE = re.compile(
    r"^\s*(?:п\.?\s*|пункт\s*)?(\d{1,2}(?:\.\d{1,2}){1,3})\s*[.)\-:]?\s*(.*)$",
    re.IGNORECASE,
)
SECTION_LINE_RE = re.compile(r"^\s*(\d{1,2})\s*[.)\-:]?\s+([^\d\s].{0,120})$")
CLAUSE_ANY_RE = re.compile(r"(?:^|\s)(\d{1,2}(?:\.\d{1,2}){1,3})\s*[.)\-:]?\s+")


def parse_clauses(text: str) -> dict:
    """
    Возвращает {"2.2": "текст пункта", ...} в порядке появления.

    Работает и когда каждый пункт на своей строке, и когда всё слито в одну
    строку (после разэкранирования JS такое бывает часто).
    """
    if not text:
        return {}
    clauses: dict = {}

    lines = text.split("\n")
    current_id = None
    buf: list[str] = []

    def flush():
        nonlocal buf, current_id
        if current_id and buf:
            body = normalize_text(" ".join(buf))
            if body and len(body) >= 3:
                clauses.setdefault(current_id, body)
        buf = []

    for line in lines:
        m = CLAUSE_LINE_RE.match(line)
        if m:
            flush()
            current_id = m.group(1)
            rest = m.group(2).strip()
            buf = [rest] if rest else []
            continue
        if current_id is not None:
            stripped = line.strip()
            if stripped:
                buf.append(stripped)
                # страховка от «склеивания» всего документа в один пункт,
                # если нумерация в тексте редкая
                if sum(len(x) for x in buf) > 2000:
                    flush()
                    current_id = None
            # Пустая строка пункт НЕ закрывает: в реальных правилах наказание
            # часто идёт отдельным абзацем после пустой строки, и раньше оно
            # терялось. Границей считается только следующий номер пункта.
    flush()

    inline = _parse_inline(text)
    # Если построчный разбор дал меньше двух пунктов, значит текст слит в одну
    # строку целиком — тогда точнее разбор «по номерам внутри строки».
    if len(clauses) < 2 and len(inline) > len(clauses):
        return inline
    # Иначе добираем пункты, приклеенные к коду: в JS-бандлах и JSON-полях
    # первая строка правил идёт сразу после «window.__DATA__ = "». Обрывки
    # короче 25 символов пропускаем — иначе в правила попадут версии вида
    # «2.5.3» из служебных строк бандла.
    for cid, body in inline.items():
        if len(body) >= 25 and cid not in clauses:
            clauses[cid] = body
    return clauses


def _parse_inline(text: str) -> dict:
    matches = list(CLAUSE_ANY_RE.finditer(text))
    if len(matches) < 2:
        return {}
    result: dict = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = normalize_text(text[start:end])
        if body and len(body) >= 3:
            result.setdefault(m.group(1), body)
    return result


def parse_sections(text: str) -> dict:
    """{"2": "Наказания", ...} — заголовки разделов."""
    sections: dict = {}
    for line in (text or "").split("\n"):
        if CLAUSE_LINE_RE.match(line):
            continue
        m = SECTION_LINE_RE.match(line)
        if m:
            title = normalize_text(m.group(2))
            if 3 <= len(title) <= 120:
                sections.setdefault(m.group(1), title)
    return sections


# ============================================================
# БАЗА ПРАВИЛ
# ============================================================
class RulesBase:
    """
    Источники правил по приоритету:
      1. локальный файл (rules.txt / rules.md / rules.json) — задаётся руками,
         работает всегда, даже если сайт недоступен;
      2. RULES_API_URL — если у сайта найдётся JSON-эндпоинт;
      3. RULES_URL — страница правил;
      4. script-бандлы этой страницы (SPA отдаёт текст из JS).
    Результат кэшируется в rules_cache.json и переживает рестарт.
    """

    def __init__(self, data_dir, url: str = DEFAULT_RULES_URL, api_url: str = "",
                 cookies: dict | None = None, headers: dict | None = None,
                 ttl_hours: int = 12):
        self.data_dir = Path(data_dir)
        self.url = url or DEFAULT_RULES_URL
        self.api_url = (api_url or "").strip()
        self.cookies = cookies or None
        self.headers = headers or None
        self.ttl_seconds = max(1, ttl_hours) * 3600

        self.clauses: dict = {}
        self.sections: dict = {}
        # Скачанные бандлы: нужны, чтобы искать в них API-пути.
        self._js_cache: dict = {}
        self.text: str = ""
        self.source: str = "нет данных"
        self.fetched_at: float = 0.0
        self.last_error: str = ""

    # ---------- состояние ----------
    @property
    def size(self) -> int:
        return len(self.clauses)

    @property
    def ready(self) -> bool:
        return bool(self.clauses) or len(self.text) > 200

    @property
    def age_hours(self) -> float:
        return (time.time() - self.fetched_at) / 3600 if self.fetched_at else -1.0

    def status_line(self) -> str:
        if not self.ready:
            return "нет данных"
        return (f"{len(self.clauses)} пунктов, {len(self.text)} симв., "
                f"источник: {self.source}, обновлено {self.age_hours:.1f} ч назад")

    def _cache_path(self) -> Path:
        return self.data_dir / "rules_cache.json"

    def local_file(self) -> Path | None:
        for name in ("rules.txt", "rules.md", "rules.json"):
            p = self.data_dir / name
            if p.exists() and p.stat().st_size > 50:
                return p
        return None

    # ---------- кэш ----------
    def load_cache(self) -> bool:
        path = self._cache_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.clauses = data.get("clauses") or {}
            self.sections = data.get("sections") or {}
            self.text = data.get("text") or ""
            self.source = (data.get("source") or "кэш") + " (кэш)"
            self.fetched_at = float(data.get("fetched_at") or 0)
            return self.ready
        except Exception as e:
            self.last_error = f"кэш правил повреждён: {e}"
            return False

    def save_cache(self):
        try:
            self._cache_path().write_text(json.dumps({
                "clauses": self.clauses,
                "sections": self.sections,
                "text": self.text[:200_000],
                "source": self.source.replace(" (кэш)", ""),
                "fetched_at": self.fetched_at,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self.last_error = f"не сохранил кэш правил: {e}"

    # ---------- загрузка ----------
    def _apply(self, text: str, source: str) -> int:
        text = normalize_text(text)
        clauses = parse_clauses(text)
        if len(clauses) < MIN_CLAUSES and len(text) < 200:
            return 0
        self.clauses = clauses
        self.sections = parse_sections(text)
        self.text = text[:200_000]
        self.source = source
        self.fetched_at = time.time()
        self.last_error = ""
        return len(clauses)

    async def refresh(self, session: aiohttp.ClientSession) -> tuple[int, str]:
        """Обновляет базу. Возвращает (сколько пунктов, человекочитаемый статус)."""
        # 1) локальный файл — приоритетный источник
        path = self.local_file()
        if path:
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                if path.suffix == ".json":
                    raw = _json_to_text(raw)
                n = self._apply(raw, path.name)
                if n or self.ready:
                    self.save_cache()
                    return n, f"локальный файл {path.name}: {n} пунктов"
            except Exception as e:
                self.last_error = f"{path.name}: {e}"

        # 2) явно заданный API правил
        if self.api_url:
            raw = await _fetch(session, self.api_url, self.cookies, self.headers)
            if raw:
                text = _json_to_text(raw) if raw.lstrip()[:1] in "[{" else raw
                n = self._apply(text, self.api_url)
                if n >= MIN_CLAUSES:
                    self.save_cache()
                    return n, f"API {self.api_url}: {n} пунктов"

        # 3-5) страница: видимый текст -> инлайн-скрипты -> внешние бандлы
        html = await _fetch(session, self.url, self.cookies, self.headers)
        if html:
            n = self._apply(html_to_text(html), self.url)
            if n >= MIN_CLAUSES:
                self.save_cache()
                return n, f"страница {self.url}: {n} пунктов"

            # У SPA текст правил часто лежит не в разметке, а в JSON внутри
            # <script> на самой странице — раньше такие скрипты не смотрели.
            n_inline, where_inline = self._scan_inline_scripts(html)
            if n_inline >= MIN_CLAUSES:
                self.save_cache()
                return n_inline, f"инлайн-скрипт {where_inline}: {n_inline} пунктов"

            found, where = await self._scan_scripts(session, html, self.url)
            if found >= MIN_CLAUSES:
                self.save_cache()
                return found, f"JS-бандл {where}: {found} пунктов"

            # Правила могут приезжать отдельным JSON-запросом: пробуем
            # API-пути, которые нашлись в коде страницы.
            for endpoint in self._api_candidates(html)[:8]:
                raw = await _fetch(session, endpoint, self.cookies, self.headers)
                if not raw:
                    continue
                data = _json_to_text(raw) if raw.lstrip()[:1] in "[{" else raw
                n_api = self._apply(data, endpoint)
                if n_api >= MIN_CLAUSES:
                    self.save_cache()
                    return n_api, f"API {endpoint}: {n_api} пунктов"

        if self.ready:
            return len(self.clauses), f"оставил прежние данные ({self.source})"
        return 0, ("не нашёл правила. Положи rules.txt в DATA_DIR "
                   "(Render: /data) — бот прочитает его")

    def _api_candidates(self, html: str = "") -> list:
        """
        Пути /api/..., найденные в разметке и в скачанных бандлах.

        Сайт — SPA: текст правил может приезжать отдельным JSON-запросом,
        а не в разметке. Поэтому ищем в коде все упоминания API и оставляем
        те, что похожи на правила или страницы.
        """
        seen, found = set(), []
        sources = list(getattr(self, "_js_cache", {}).values())
        if html:
            sources.append(html)
        for text in sources:
            for path in re.findall(r'["\'`](/api/[A-Za-z0-9_/\-\.]{2,60})["\'`]', text):
                if path in seen:
                    continue
                seen.add(path)
                if any(hint in path.lower() for hint in API_HINTS):
                    found.append(urljoin(self.url, path))
        return found

    def _scan_inline_scripts(self, html: str) -> tuple[int, str]:
        """
        Ищет правила внутри <script>...</script> на самой странице.

        Так делают Nuxt/Vue/Next: текст страницы приезжает в JSON-поле внутри
        инлайнового скрипта, а в разметке его нет. Раньше эти скрипты не
        проверялись вообще.
        """
        best = 0
        best_text = ""
        best_idx = 0
        pattern = r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>"
        for idx, body in enumerate(re.findall(pattern, html, re.IGNORECASE | re.DOTALL)):
            if len(body) < 80:
                continue
            text = js_to_text(body)
            found = len(parse_clauses(text))
            if found > best:
                best, best_text, best_idx = found, text, idx
        if best:
            self._apply(best_text, f"{self.url} (инлайн #{best_idx})")
        return best, f"#{best_idx}"

    async def _scan_scripts(self, session, html: str, base_url: str) -> tuple[int, str]:
        """Обходит внешние бандлы и один уровень чанков, на которые они ссылаются."""
        srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        queue = [urljoin(base_url, s) for s in srcs[:12]]
        seen, lazy = set(), []
        best, best_src = 0, ""
        while queue or lazy:
            full = queue.pop(0) if queue else lazy.pop(0)
            if full in seen:
                continue
            seen.add(full)
            js = await _fetch(session, full, self.cookies, self.headers)
            if not js:
                continue
            self._js_cache[full] = js
            text = js_to_text(js)
            clauses = parse_clauses(text)
            if len(clauses) > best:
                best = len(clauses)
                best_src = full.split("/")[-1][:40]
                if best >= MIN_CLAUSES:
                    self._apply(text, full)
                    return best, best_src
            # ленивые чанки: бандл ссылается на файлы, которых нет в разметке
            if len(lazy) < 10:
                for ref in re.findall(r'["\']([\w./-]{3,60}\.js)["\']', js):
                    cand = urljoin(full, ref)
                    if cand not in seen and cand not in lazy and cand not in queue:
                        lazy.append(cand)
        return best, best_src

    async def probe(self, session) -> list:
        """Диагностика: что именно нашлось в каждом источнике правил."""
        lines = [f"URL страницы: {self.url}",
                 f"API правил: {self.api_url or '—'}"]
        local = self.local_file()
        lines.append(f"локальный файл: {local.name if local else 'нет'}")
        html = await _fetch(session, self.url, self.cookies, self.headers)
        if not html:
            lines.append("страница: НЕ загрузилась")
            return lines
        lines.append(f"страница: {len(html)} символов")
        text = html_to_text(html)
        lines.append(f"  видимый текст: {len(text)} симв., пунктов {len(parse_clauses(text))}")
        inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                            html, re.IGNORECASE | re.DOTALL)
        lines.append(f"  инлайновых скриптов: {len(inline)}")
        for idx, body in enumerate(inline[:6]):
            if len(body) < 80:
                continue
            js_text = js_to_text(body)
            lines.append(f"    #{idx}: {len(body)} симв., пунктов {len(parse_clauses(js_text))}")
        srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        lines.append(f"  внешних скриптов: {len(srcs)}")
        for src in srcs[:10]:
            full = urljoin(self.url, src)
            js = await _fetch(session, full, self.cookies, self.headers)
            name = src.split("/")[-1][:30]
            if not js:
                lines.append(f"    {name}: не загрузился")
                continue
            self._js_cache[full] = js
            js_text = js_to_text(js)
            lines.append(f"    {name}: {len(js)} симв., пунктов {len(parse_clauses(js_text))}")
            refs = sorted(set(re.findall(r'["\']([\w./-]{3,60}\.js)["\']', js)))
            if refs:
                lines.append(f"      ссылки на чанки: {', '.join(refs[:6])}")

        candidates = self._api_candidates(html)
        lines.append(f"  найдено API-путей: {len(candidates)}")
        for url in candidates[:15]:
            lines.append(f"    {url}")
        if not candidates:
            lines.append("    (ни одного /api/... в коде страницы не видно)")
        for url in candidates[:8]:
            raw = await _fetch(session, url, self.cookies, self.headers)
            if not raw:
                continue
            data = _json_to_text(raw) if raw.lstrip()[:1] in "[{" else raw
            n_found = len(parse_clauses(data))
            lines.append(f"    ✓ {url}: {len(raw)} симв., пунктов {n_found}")
        return lines

    # ---------- поиск ----------
    def lookup(self, query: str, limit: int = 6) -> dict:
        """
        Ищет ответ по правилам.
        Возвращает {"exact": (id, text) | None, "matches": [(id, text, score)],
                    "section": (id, title) | None}.
        """
        q = normalize_text(query or "").casefold()
        result = {"exact": None, "matches": [], "section": None}
        if not q:
            return result

        # прямой номер пункта: «2.2», «что такое 2.2», «п.2.2»
        m = re.search(r"\b(\d{1,2}(?:\.\d{1,2}){1,3})\b", q)
        if m:
            cid = m.group(1)
            if cid in self.clauses:
                result["exact"] = (cid, self.clauses[cid])

        # раздел целиком: «раздел 2», «правила 2»
        ms = re.search(r"(?:раздел|глава|пункт)?\s*(\d{1,2})(?:\s|$)", q)
        if ms and ms.group(1) in self.sections:
            result["section"] = (ms.group(1), self.sections[ms.group(1)])

        if not result["exact"]:
            tokens = [t for t in re.findall(r"[а-яёa-z0-9]{4,}", q)]
            scored = []
            for cid, body in self.clauses.items():
                low = body.casefold()
                score = sum(low.count(t) for t in tokens)
                if score:
                    scored.append((cid, body, score))
            scored.sort(key=lambda x: (-x[2], len(x[0])))
            result["matches"] = scored[:limit]
        return result

    def context_for(self, query: str, limit: int = 6, max_chars: int = 12000) -> str:
        """Фрагмент правил для промпта: найденные пункты, иначе начало правил."""
        found = self.lookup(query, limit)
        chunks: list[str] = []
        if found["section"]:
            chunks.append(f"РАЗДЕЛ {found['section'][0]}: {found['section'][1]}")
        if found["exact"]:
            cid, body = found["exact"]
            chunks.append(f"ПУНКТ {cid}: {body}")
        for cid, body, _score in found["matches"]:
            chunks.append(f"ПУНКТ {cid}: {body}")
        if not chunks:
            chunks.append("ТЕКСТ ПРАВИЛ (начало):\n" + self.text[:max_chars])
        text = "\n".join(chunks)
        return text[:max_chars]

    def clause_ids(self) -> list:
        return sorted(self.clauses, key=_clause_sort_key)


def _clause_sort_key(cid: str):
    return tuple(int(p) for p in cid.split(".") if p.isdigit())


def _json_to_text(raw: str) -> str:
    """Достаёт длинные текстовые значения из произвольного JSON."""
    try:
        data = json.loads(raw)
    except Exception:
        return raw
    parts: list[str] = []

    def walk(node, depth=0):
        if depth > 8:
            return
        if isinstance(node, str):
            if len(node) > 60:
                parts.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    walk(data)
    return "\n\n".join(parts) if parts else raw


async def _fetch(session, url: str, cookies=None, headers=None,
                 limit: int = MAX_FETCH_BYTES) -> str | None:
    try:
        async with session.get(url, cookies=cookies, headers=headers) as r:
            if r.status != 200:
                return None
            raw = await r.content.read(limit)
            charset = r.charset or "utf-8"
            try:
                return raw.decode(charset, errors="replace")
            except LookupError:
                return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


# ============================================================
# КЛИЕНТ GEMINI
# ============================================================
class GeminiClient:
    """
    Обёртка над Interactions API.
    POST {api_url} с заголовком x-goog-api-key, тело:
        {"model": ..., "input": ..., "system_instruction": ..., "store": false}
    Текст ответа лежит в steps[type=model_output].content[type=text].text
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, api_url: str = DEFAULT_API_URL,
                 timeout: float = 45.0, max_output_tokens: int = 900, thinking_level: str = ""):
        self.api_key = (api_key or "").strip()
        self.model = model or DEFAULT_MODEL
        self.api_url = api_url or DEFAULT_API_URL
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.thinking_level = (thinking_level or "").strip()

        self.requests = 0
        self.failures = 0
        self.last_error = ""
        self.last_latency = 0.0
        self.last_usage: dict = {}
        self._sem = asyncio.Semaphore(2)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    def status_line(self) -> str:
        if not self.enabled:
            return "выключен (нет GEMINI_API_KEY)"
        state = "работает" if not self.last_error else f"ошибка: {self.last_error[:120]}"
        return (f"включён, модель {self.model}, запросов {self.requests}, "
                f"ошибок {self.failures} — {state}")

    @staticmethod
    def parse_response(data: dict) -> tuple[str | None, str]:
        """(текст, причина_если_пусто)."""
        if not isinstance(data, dict):
            return None, "ответ не JSON-объект"
        status = str(data.get("status") or "")
        parts: list[str] = []
        for step in data.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if step.get("type") not in ("model_output", None):
                continue
            for item in step.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
        text = "\n".join(parts).strip()
        if text:
            return text, ""
        if status and status not in ("completed", "in_progress"):
            return None, f"status={status}"
        return None, f"в ответе нет текста (status={status or '?'})"

    async def ask(self, session, prompt: str, system: str = "",
                  max_output_tokens: int | None = None) -> tuple[str | None, dict]:
        """
        Возвращает (текст | None, метаданные).
        meta: {"ok", "latency", "error", "usage", "status"}
        """
        meta = {"ok": False, "latency": 0.0, "error": "", "usage": {}, "status": ""}
        if not self.enabled:
            meta["error"] = "нет GEMINI_API_KEY"
            return None, meta
        if not prompt:
            meta["error"] = "пустой запрос"
            return None, meta

        body: dict = {
            "model": self.model,
            "input": prompt,
            "store": False,
            "generation_config": {
                "max_output_tokens": max_output_tokens or self.max_output_tokens,
            },
        }
        if system:
            body["system_instruction"] = system
        if self.thinking_level:
            body["generation_config"]["thinking_level"] = self.thinking_level

        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        started = time.perf_counter()
        self.requests += 1
        try:
            async with self._sem:
                async with session.post(self.api_url, json=body, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=self.timeout)) as r:
                    meta["latency"] = time.perf_counter() - started
                    raw = await r.text()
                    if r.status != 200:
                        meta["error"] = f"HTTP {r.status}: {raw[:300]}"
                        low = raw.lower()
                        if "not found" in low or "unsupported" in low or "invalid" in low:
                            meta["error"] += (" → проверь переменную AI_MODEL, "
                                              "например `gemini-3.8-flash`")
                        meta["status"] = str(r.status)
                        self.failures += 1
                        self.last_error = meta["error"]
                        return None, meta
                    try:
                        data = json.loads(raw)
                    except Exception as e:
                        meta["error"] = f"не разобрал JSON: {e}; начало: {raw[:200]}"
                        self.failures += 1
                        self.last_error = meta["error"]
                        return None, meta
        except asyncio.TimeoutError:
            meta["latency"] = time.perf_counter() - started
            meta["error"] = f"таймаут {self.timeout:.0f} с"
            self.failures += 1
            self.last_error = meta["error"]
            return None, meta
        except Exception as e:
            meta["latency"] = time.perf_counter() - started
            meta["error"] = f"{type(e).__name__}: {e}"
            self.failures += 1
            self.last_error = meta["error"]
            return None, meta

        text, why = self.parse_response(data)
        meta["status"] = str(data.get("status") or "")
        meta["usage"] = data.get("usage") or {}
        self.last_latency = meta["latency"]
        self.last_usage = meta["usage"]
        if text is None:
            meta["error"] = why
            self.failures += 1
            self.last_error = why
            return None, meta

        meta["ok"] = True
        self.last_error = ""
        return text, meta


# ============================================================
# ПРОМПТЫ
# ============================================================
RULES_SYSTEM = (
    "Ты помощник Discord-бота клана TALENT на игровом проекте cs2red.ru (CS2). "
    "Отвечай по-русски, кратко и по делу (до 900 символов). "
    "Опирайся ТОЛЬКО на текст правил из запроса. Обязательно указывай номера пунктов. "
    "Если ответа в правилах нет — честно скажи, что этого пункта в правилах нет, "
    "и не выдумывай. Не давай юридических советов."
)

SRE_SYSTEM = (
    "Ты SRE-помощник, разбираешь ошибки Python-бота для Discord. "
    "По списку ошибок и диагностике дай: 1) что именно сломалось; "
    "2) наиболее вероятную причину; 3) конкретное действие для починки. "
    "Пиши по-русски, кратко, без воды и без повторения трейсбеков целиком. "
    "Если ошибки не связаны между собой — скажи об этом."
)

ASK_SYSTEM = (
    "Ты дружелюбный помощник Discord-сообщества клана TALENT по игре CS2 "
    "на проекте cs2red.ru. Отвечай по-русски, кратко (до 900 символов), по делу, "
    "без выдумок. Если в контексте есть правила проекта и вопрос про правила — "
    "обязательно ссылайся на номера пунктов. Если не знаешь ответа — скажи прямо."
)


def build_rules_prompt(question: str, context: str, known_ids: list | None = None) -> str:
    ids = ""
    if known_ids:
        ids = ("\n\nСПИСОК СУЩЕСТВУЮЩИХ ПУНКТОВ: " + ", ".join(known_ids[:120]))
    return (f"ТЕКСТ ПРАВИЛ (фрагменты):\n{context}{ids}\n\n"
            f"ВОПРОС ИГРОКА: {question}\n\n"
            f"Ответь кратко и со ссылкой на номера пунктов.")


def build_error_prompt(errors: list, diagnostics: str = "") -> str:
    lines = []
    for e in errors:
        lines.append(f"[{e.get('time', '?')}] {e.get('context', '?')}: {e.get('error', '?')}")
        tb = (e.get("traceback") or "").strip()
        if tb:
            lines.append("  " + tb.replace("\n", "\n  ")[:900])
    body = "\n".join(lines) or "ошибок нет"
    return (f"ДИАГНОСТИКА БОТА:\n{diagnostics}\n\n"
            f"ОШИБКИ С МОМЕНТА ПРОШЛОГО РАЗБОРА ({len(errors)}):\n{body}")


# ============================================================
# АЛЬТЕРНАТИВНЫЙ ПРОВАЙДЕР: OpenAI-совместимый API
# ============================================================
DEFAULT_OPENAI_BASE = "https://api.llm7.io/v1"


class OpenAICompatClient:
    """
    Клиент для OpenAI-совместимых API: LLM7, OpenRouter, локальный прокси.
    Тот же интерфейс, что у GeminiClient (enabled/status_line/ask), поэтому
    код бота не знает, какой провайдер используется.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini",
                 base_url: str = DEFAULT_OPENAI_BASE, timeout: float = 45.0,
                 max_output_tokens: int = 900):
        self.api_key = (api_key or "").strip()
        self.model = model or "gpt-4o-mini"
        self.base_url = (base_url or DEFAULT_OPENAI_BASE).rstrip("/")
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens

        self.requests = 0
        self.failures = 0
        self.last_error = ""
        self.last_latency = 0.0
        self.last_usage: dict = {}
        self._sem = asyncio.Semaphore(2)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def provider_name(self) -> str:
        return "openai-совместимый"

    def status_line(self) -> str:
        if not self.enabled:
            return "выключен (нет AI_API_KEY/LLM7_API_KEY)"
        state = "работает" if not self.last_error else f"ошибка: {self.last_error[:120]}"
        return (f"включён ({self.provider_name}), модель {self.model}, "
                f"{self.base_url}, запросов {self.requests}, ошибок {self.failures} — {state}")

    @staticmethod
    def parse_response(data: dict) -> tuple[str | None, str]:
        if not isinstance(data, dict):
            return None, "ответ не JSON-объект"
        if isinstance(data.get("error"), (dict, str)):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else err
            return None, f"API вернул ошибку: {str(msg)[:200]}"
        choices = data.get("choices") or []
        if not choices:
            return None, "в ответе нет choices"
        msg = (choices[0] or {}).get("message") or {}
        text = str(msg.get("content") or "").strip()
        if text:
            return text, ""
        return None, "пустой content в ответе"

    async def ask(self, session, prompt: str, system: str = "",
                  max_output_tokens: int | None = None) -> tuple[str | None, dict]:
        meta = {"ok": False, "latency": 0.0, "error": "", "usage": {}, "status": ""}
        if not self.enabled:
            meta["error"] = "нет API-ключа"
            return None, meta
        if not prompt:
            meta["error"] = "пустой запрос"
            return None, meta

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_output_tokens or self.max_output_tokens,
        }
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        started = time.perf_counter()
        self.requests += 1
        try:
            async with self._sem:
                async with session.post(url, json=body, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=self.timeout)) as r:
                    meta["latency"] = time.perf_counter() - started
                    raw = await r.text()
                    if r.status != 200:
                        meta["error"] = f"HTTP {r.status}: {raw[:300]}"
                        low = raw.lower()
                        if ("unavailable" in low or "model_not_found" in low
                                or "does not exist" in low or "unknown model" in low):
                            meta["error"] += (" → проверь переменную AI_MODEL. "
                                              "У LLM7 подходят селекторы "
                                              "`default`, `fast` или `pro`; "
                                              f"полный список: {self.base_url}/models")
                        meta["status"] = str(r.status)
                        self.failures += 1
                        self.last_error = meta["error"]
                        return None, meta
                    try:
                        data = json.loads(raw)
                    except Exception as e:
                        meta["error"] = f"не разобрал JSON: {e}; начало: {raw[:200]}"
                        self.failures += 1
                        self.last_error = meta["error"]
                        return None, meta
        except asyncio.TimeoutError:
            meta["latency"] = time.perf_counter() - started
            meta["error"] = f"таймаут {self.timeout:.0f} с"
            self.failures += 1
            self.last_error = meta["error"]
            return None, meta
        except Exception as e:
            meta["latency"] = time.perf_counter() - started
            meta["error"] = f"{type(e).__name__}: {e}"
            self.failures += 1
            self.last_error = meta["error"]
            return None, meta

        text, why = self.parse_response(data)
        meta["usage"] = data.get("usage") or {}
        self.last_latency = meta["latency"]
        self.last_usage = meta["usage"]
        if text is None:
            meta["error"] = why
            self.failures += 1
            self.last_error = why
            return None, meta
        meta["ok"] = True
        self.last_error = ""
        return text, meta


def _default_openai_model(base_url: str) -> str:
    """
    Модель по умолчанию для OpenAI-совместимого провайдера.

    У LLM7 нет имён моделей в стиле OpenAI — там селекторы
    `default`, `fast`, `pro` (см. https://docs.llm7.io/guides/models).
    Поэтому для api.llm7.io берём `default`, а для остальных провайдеров
    оставляем привычное имя.
    """
    if "llm7" in (base_url or "").lower():
        return "default"
    return "gpt-4o-mini"


def make_ai_client(provider: str = "auto", *, gemini_key: str = "", openai_key: str = "",
                   model: str = "", base_url: str = "", api_url: str = "",
                   timeout: float = 45.0, max_output_tokens: int = 900,
                   thinking_level: str = ""):
    """
    Выбирает провайдера:
      gemini — Gemini Interactions API (нужен GEMINI_API_KEY);
      openai — OpenAI-совместимый (LLM7_API_KEY / AI_API_KEY / OPENROUTER_API_KEY);
      auto   — gemini, если есть его ключ, иначе openai.
    """
    provider = (provider or "auto").strip().lower()
    if provider not in ("gemini", "openai", "auto"):
        provider = "auto"
    if provider == "auto":
        provider = "gemini" if gemini_key else ("openai" if openai_key else "gemini")

    if provider == "openai":
        resolved_base = base_url or DEFAULT_OPENAI_BASE
        return OpenAICompatClient(
            openai_key,
            model=model or _default_openai_model(resolved_base),
            base_url=resolved_base,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )
    return GeminiClient(
        gemini_key,
        model=model or DEFAULT_MODEL,
        api_url=api_url or DEFAULT_API_URL,
        timeout=timeout,
        max_output_tokens=max_output_tokens,
        thinking_level=thinking_level,
    )
