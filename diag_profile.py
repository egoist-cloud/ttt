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

# публичные/профильные эндпоинты (могут не требовать админ-кук)
cands = [
    f"https://cs2red.ru/api/profile/{steam_id}",
    f"https://cs2red.ru/api/user/{steam_id}",
    f"https://cs2red.ru/api/data/profile/{steam_id}",
    f"https://cs2red.ru/api/data/profile?steamid64={steam_id}",
    f"https://cs2red.ru/api/data/profile?userId={uid}",
    f"https://cs2red.ru/api/vips?userId={uid}",
    f"https://cs2red.ru/api/vips?steamid64={steam_id}",
    f"https://cs2red.ru/api/data/vips?userId={uid}",
    f"https://cs2red.ru/api/data/vips?steamid64={steam_id}",
    f"https://cs2red.ru/api/admin/vips?userId={uid}",
    f"https://cs2red.ru/api/user/{uid}/vips",
    f"https://cs2red.ru/api/data/user/{uid}/vips",
    f"https://cs2red.ru/api/stats/{steam_id}",
    f"https://cs2red.ru/api/data/stats/{steam_id}",
    f"https://cs2red.ru/api/statistics/{steam_id}",
    f"https://cs2red.ru/api/data/statistics/{steam_id}",
    f"https://cs2red.ru/api/playtime/{steam_id}",
    f"https://cs2red.ru/api/data/playtime/{steam_id}",
    f"https://cs2red.ru/api/data/servers/{steam_id}",
    f"https://cs2red.ru/api/data/sessions/{steam_id}",
    f"https://cs2red.ru/api/data/history/{steam_id}",
    f"https://cs2red.ru/api/data/actions/{steam_id}",
    f"https://cs2red.ru/api/data/activity/{steam_id}",
]
for ep in cands:
    try:
        r = requests.get(ep, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=10)
        txt = r.text[:220].replace("\n", " ")
        if r.status_code == 200 and "success\":false" not in r.text[:120]:
            print(f"{r.status_code} {ep}\n      {txt}")
        else:
            print(f"{r.status_code} {ep} -> (skip)")
    except Exception as e:
        print(f"EXC {ep}: {e}")