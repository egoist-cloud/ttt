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

# 1) stats с поиском по steamid
for params in [
    {"begin": 0, "count": 1, "search": steam_id},
    {"begin": 0, "count": 1, "userId": 135587},
    {"begin": 0, "count": 1, "steamid64": steam_id},
    {"begin": 0, "count": 1, "nick": "Белочка"},
]:
    try:
        r = requests.get("https://cs2red.ru/api/data/stats", params=params,
                         cookies=CS2RED_COOKIES, headers=HEADERS, timeout=12)
        j = r.json()
        st = j.get("stats", [])
        if st:
            s = st[0]
            # проверим на вложенный "user" его поля
            u = s.get("user", {})
            print("FOUND:", params, "| user keys:", list(u.keys()))
            # есть ли время где-то?
            print("   playtime/time в stats:", {k: v for k, v in s.items() if "time" in k.lower() or "play" in k.lower()})
            break
        else:
            print("empty:", params, r.status_code)
    except Exception as e:
        print("EXC", params, e)

# 2) посмотрим популярные эндпоинты на наличие времени
extra = [
    "https://cs2red.ru/api/data/top",
    "https://cs2red.ru/api/data/rating",
    "https://cs2red.ru/api/data/leaderboard",
    "https://cs2red.ru/api/data/activity",
    "https://cs2red.ru/api/data/playtime/{sid}",
    "https://cs2red.ru/api/data/players",
    "https://cs2red.ru/api/data/sessions",
    "https://cs2red.ru/api/data/session",
]
for ep in extra:
    url = ep.replace("{sid}", "135587")
    try:
        r = requests.get(url, params={"begin": 0, "count": 2},
                         cookies=CS2RED_COOKIES, headers=HEADERS, timeout=10)
        print(f"{r.status_code} {ep} -> {r.text[:150]}")
    except Exception as e:
        print(f"EXC {ep}: {e}")