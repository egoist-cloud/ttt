# -*- coding: utf-8 -*-
"""
Сохранение данных бота в GitHub.

Зачем: на Render файловая система контейнера временная, поэтому привязки
Discord↔Steam и прочие JSON-базы теряются при каждом деплое и рестарте.
Persistent Disk решает это полностью, но если диска нет — данные можно
держать в отдельном репозитории GitHub.

Как работает:
  * pull() — при старте подтягивает отсутствующие локально файлы;
  * push() — выгружает изменившиеся файлы (только реально изменённые,
    сравниваются хеши, чтобы не спамить коммитами);
  * в сообщение коммита по умолчанию добавляется "[skip render]", чтобы
    Render не перезапускал бота из-за коммита с данными.

API: GitHub Contents API (https://docs.github.com/rest/repos/contents).
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

DEFAULT_API = "https://api.github.com"
MAX_CONTENT_BYTES = 900_000  # больше Contents API за один запрос не примет


class GitHubSync:
    def __init__(self, token: str, repo: str, branch: str = "main", base_path: str = "",
                 api: str = DEFAULT_API, timeout: float = 30.0,
                 commit_prefix: str = "bot data", skip_render: bool = True):
        self.token = (token or "").strip()
        self.repo = (repo or "").strip().strip("/")
        self.branch = (branch or "main").strip() or "main"
        self.base_path = (base_path or "").strip().strip("/")
        self.api = (api or DEFAULT_API).rstrip("/")
        self.timeout = timeout
        self.commit_prefix = commit_prefix
        self.skip_render = skip_render

        self.last_error = ""
        self.pushed_total = 0
        self.pulled_total = 0
        self._sha: dict = {}    # имя файла -> sha в репозитории
        self._hash: dict = {}   # имя файла -> хеш последнего отправленного содержимого

    # ---------- состояние ----------
    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo)

    def status_line(self) -> str:
        if not self.enabled:
            missing = []
            if not self.token:
                missing.append("GITHUB_TOKEN")
            if not self.repo:
                missing.append("GITHUB_REPO")
            return f"выключен (нет {', '.join(missing)})"
        state = "работает" if not self.last_error else f"ошибка: {self.last_error[:120]}"
        return (f"включён, {self.repo}@{self.branch}, отправлено {self.pushed_total}, "
                f"получено {self.pulled_total} — {state}")

    def _path(self, name: str) -> str:
        return f"{self.base_path}/{name}" if self.base_path else name

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    # ---------- низкий уровень ----------
    async def _get(self, session, path: str):
        """(содержимое | None, sha | None). 404 — файла нет."""
        url = f"{self.api}/repos/{self.repo}/contents/{path}"
        try:
            async with session.get(url, headers=self._headers(),
                                   params={"ref": self.branch}) as r:
                raw = await r.text()
                if r.status == 404:
                    return None, None
                if r.status != 200:
                    self.last_error = f"GET {path}: HTTP {r.status} {raw[:200]}"
                    return None, None
                data = json.loads(raw)
                content = base64.b64decode(data.get("content") or "").decode("utf-8")
                return content, data.get("sha")
        except Exception as e:
            self.last_error = f"GET {path}: {type(e).__name__}: {e}"
            return None, None

    async def _put(self, session, path: str, content: str, sha, message: str):
        url = f"{self.api}/repos/{self.repo}/contents/{path}"
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha
        try:
            async with session.put(url, headers=self._headers(), json=body) as r:
                raw = await r.text()
                if r.status in (200, 201):
                    try:
                        return True, json.loads(raw).get("content", {}).get("sha")
                    except Exception:
                        return True, sha
                self.last_error = f"PUT {path}: HTTP {r.status} {raw[:200]}"
                return False, None
        except Exception as e:
            self.last_error = f"PUT {path}: {type(e).__name__}: {e}"
            return False, None

    # ---------- высокий уровень ----------
    async def pull(self, session, filenames, local_dir, overwrite: bool = False) -> list:
        """
        Скачивает файлы, которых нет локально (или все, если overwrite=True).
        Возвращает список имён, которые реально записались.
        """
        if not self.enabled:
            return []
        local_dir = Path(local_dir)
        saved = []
        for name in filenames:
            target = local_dir / name
            if target.exists() and not overwrite and target.stat().st_size > 0:
                continue
            content, sha = await self._get(session, self._path(name))
            if content is None:
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except Exception as e:
                self.last_error = f"запись {name}: {e}"
                continue
            self._sha[name] = sha
            self._hash[name] = _hash_text(content)
            saved.append(name)
            self.pulled_total += 1
        return saved

    async def push(self, session, filenames, local_dir) -> tuple[int, str]:
        """
        Отправляет изменившиеся файлы. Возвращает (сколько отправлено, статус).
        """
        if not self.enabled:
            return 0, "GitHub-синк выключен"
        local_dir = Path(local_dir)
        sent, skipped, failed = [], 0, []
        for name in filenames:
            source = local_dir / name
            if not source.exists():
                continue
            try:
                content = source.read_text(encoding="utf-8")
            except Exception as e:
                failed.append(f"{name} ({e})")
                continue
            if not content.strip():
                skipped += 1
                continue
            if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
                failed.append(f"{name} (файл больше {MAX_CONTENT_BYTES // 1000} КБ)")
                continue

            digest = _hash_text(content)
            if self._hash.get(name) == digest:
                skipped += 1
                continue

            if name not in self._sha:
                _old, sha = await self._get(session, self._path(name))
                self._sha[name] = sha

            message = f"{self.commit_prefix}: {name}"
            if self.skip_render:
                message += " [skip render]"

            ok, new_sha = await self._put(session, self._path(name), content,
                                          self._sha.get(name), message)
            if not ok and "409" in (self.last_error or ""):
                # конфликт sha: кто-то изменил файл в репозитории — берём актуальный sha
                _old, sha = await self._get(session, self._path(name))
                ok, new_sha = await self._put(session, self._path(name), content, sha, message)
            if ok:
                self._sha[name] = new_sha
                self._hash[name] = digest
                sent.append(name)
                self.pushed_total += 1
            else:
                failed.append(name)

        parts = []
        if sent:
            parts.append("отправлено: " + ", ".join(sent))
        if skipped:
            parts.append(f"без изменений: {skipped}")
        if failed:
            parts.append("не удалось: " + ", ".join(failed))
        return len(sent), (self.last_error if failed and not sent
                           else "; ".join(parts) or "нечего отправлять")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
