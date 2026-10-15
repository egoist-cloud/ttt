# -*- coding: utf-8 -*-
"""
Безопасный ремонт JSON-баз.

Что изменилось: прежняя версия фильтровала значения по «17 цифр» и тем самым
БЕЗВОЗВРАТНО выбрасывала ники из mass_links.json (97 записей). Теперь ничего
не фильтруется — только убираются висячие запятые, а исходник сохраняется в .bak.

Запуск:  python fix_json.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

FILES = ["links.json", "mass_links.json", "players_db.json", "moderators.json",
         "users_db.json", "votes.json", "seen.json", "pending_links.json"]

for name in FILES:
    path = Path(name)
    if not path.exists():
        continue
    raw = path.read_text(encoding="utf-8")
    try:
        json.loads(raw)
        print(f"OK      {name}")
        continue
    except json.JSONDecodeError as e:
        print(f"BROKEN  {name}: {e.msg} (строка {e.lineno})")
    fixed = re.sub(r",(\s*[}\]])", r"\1", raw)
    try:
        json.loads(fixed)
    except json.JSONDecodeError as e:
        print(f"        не починил автоматически: {e.msg} (строка {e.lineno})")
        print("        правь вручную, файл не тронут")
        continue
    shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(fixed, encoding="utf-8")
    print(f"FIXED   {name} (исходник сохранён в {path.name}.bak)")
