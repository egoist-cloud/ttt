import requests
import os
import sys
import json
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()

CS2RED_COOKIES = {
    "token": os.getenv("CS2RED_TOKEN", ""),
    "bh": os.getenv("CS2RED_BH", ""),
    "_yasc": os.getenv("CS2RED_YASC", ""),
    "browser_id": os.getenv("CS2RED_BROWSER_ID", ""),
    "yandexuid": os.getenv("CS2RED_YANDEXUID", ""),
}
HEADERS = {
    "User-Agent": "Mozilla/5.0", "Accept": "*/*",
    "Referer": "https://cs2red.ru/admin", "Origin": "https://cs2red.ru",
}

steam_id = "76561199017448448"

# 1) полная структура stats без поиска: посмотрим на все поля
r = requests.get("https://cs2red.ru/api/data/stats",
                 params={"begin": 0, "count": 1},
                 cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
j = r.json()
stats = j.get("stats", [])
if stats:
    s = stats[0]
    print("Поля stats:", list(s.keys()))
    print(json.dumps(s, ensure_ascii=False, indent=1)[:1400])

# 2) попробуем поиск поиском по нику "Белочка" чтобы получить userId и возможно время
r2 = requests.get("https://cs2red.ru/api/data/stats",
                  params={"begin": 0, "count": 1, "search": "Белочка"},
                  cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
j2 = r2.json()
st2 = j2.get("stats", [])
if st2:
    print("\n--- по поиску ---")
    print(json.dumps(st2[0], ensure_ascii=False, indent=1)[:1400])