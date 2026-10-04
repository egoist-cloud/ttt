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
    "Referer": "https://cs2red.ru", "Origin": "https://cs2red.ru",
}

steam_id = "76561199017448448"
uid = 135587

# вероятные эндпоинты: услуги/магазин/VIP/время игрока
cands = [
    f"https://cs2red.ru/api/data/services?userId={uid}",
    f"https://cs2red.ru/api/data/privileges?userId={uid}",
    f"https://cs2red.ru/api/data/shop?userId={uid}",
    f"https://cs2red.ru/api/data/shop/items?userId={uid}",
    f"https://cs2red.ru/api/data/shop/user?userId={uid}",
    f"https://cs2red.ru/api/data/items?userId={uid}",
    f"https://cs2red.ru/api/shop?userId={uid}",
    f"https://cs2red.ru/api/services?userId={uid}",
    f"https://cs2red.ru/api/data/player?steamid64={steam_id}",
    f"https://cs2red.ru/api/data/player/{steam_id}",
    f"https://cs2red.ru/api/data/player/time?steamid64={steam_id}",
    f"https://cs2red.ru/api/data/time/{steam_id}",
    f"https://cs2red.ru/api/data/onlinetime/{steam_id}",
    f"https://cs2red.ru/api/data/stat/time/{steam_id}",
    f"https://cs2red.ru/api/data/statistics/user/{steam_id}",
    f"https://cs2red.ru/api/data/user-stats/{steam_id}",
    f"https://cs2red.ru/api/data/profile/stats/{steam_id}",
    f"https://cs2red.ru/api/data/steam/{steam_id}",
    f"https://cs2red.ru/api/data/online/{steam_id}",
    f"https://cs2red.ru/api/data/connection/{steam_id}",
]
for ep in cands:
    try:
        r = requests.get(ep, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            print(f"200 {ep}\n   {r.text[:400]}\n")
        else:
            print(f"{r.status_code} {ep}")
    except Exception as e:
        print(f"EXC {ep}: {e}")

# также проверим: в /api/data/servers уже есть "time" игроков on-line. Посмотрим глубину.
print("\n--- servers data пример (players.time) ---")
r = requests.get("https://cs2red.ru/api/data/servers", cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
servers = r.json().get("servers", [])
non_empty = [s for s in servers if s.get("data")]
if non_empty:
    d = json.loads(non_empty[0]["data"])
    print("ключи data:", list(d.keys()))
    if d.get("players"):
        print("игрок:", json.dumps(d["players"][0], ensure_ascii=False))