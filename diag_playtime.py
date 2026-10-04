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

# 1) ищем userId
r = requests.get("https://cs2red.ru/api/admin/users",
                 params={"begin": 0, "count": 1, "search": steam_id},
                 cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
j = r.json()
u = (j.get("users") or [None])[0]
uid = u.get("id") if u else None
print("userId:", uid)

# 2) пробуем админ-эндпоинты с userId (может, вернутся детали с VIP/время)
candidates = [
    f"https://cs2red.ru/api/admin/user?userId={uid}",
    f"https://cs2red.ru/api/admin/user/{uid}",
    f"https://cs2red.ru/api/admin/users/{uid}",
    f"https://cs2red.ru/api/user/{uid}",
    f"https://cs2red.ru/api/data/user/{uid}",
    f"https://cs2red.ru/api/data/stats?userId={uid}",
    f"https://cs2red.ru/api/data/stats/{uid}",
]
for ep in candidates:
    try:
        rr = requests.get(ep, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
        print(f"\n{rr.status_code} {ep}")
        if rr.status_code == 200:
            print(rr.text[:900])
    except Exception as e:
        print(f"EXC {ep}: {e}")

# 3) проверим data/servers: структура и есть ли time/players
print("\n--- servers структура ---")
r2 = requests.get("https://cs2red.ru/api/data/servers", cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
servers = r2.json().get("servers", [])
print("серверов:", len(servers))
if servers:
    print("ключи сервера:", list(servers[0].keys()))
    print(json.dumps(servers[0], ensure_ascii=False)[:800])