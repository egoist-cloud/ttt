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

candidates = [
    "https://cs2red.ru/api/data/vips",
    "https://cs2red.ru/api/data/vip",
    "https://cs2red.ru/api/data/servers",
    "https://cs2red.ru/api/servers",
    "https://cs2red.ru/api/admin/servers",
    "https://cs2red.ru/api/data/stats",
    "https://cs2red.ru/api/data/playtime",
    "https://cs2red.ru/api/data/time",
    "https://cs2red.ru/api/data/users",
    "https://cs2red.ru/api/data/admins",
    "https://cs2red.ru/api/data/bans",
    "https://cs2red.ru/api/data/mutes",
    "https://cs2red.ru/api/data/online",
    "https://cs2red.ru/api/data/servers/{sid}/players",
]

for ep in candidates:
    url = ep.replace("{sid}", "1")
    try:
        r = requests.get(url, params={"begin": 0, "count": 3, "search": steam_id},
                         cookies=CS2RED_COOKIES, headers=HEADERS, timeout=10)
        txt = r.text[:200].replace("\n", " ")
        print(f"{r.status_code:>4}  {ep}")
        if r.status_code == 200:
            print(f"      {txt}")
    except Exception as e:
        print(f" EXC  {ep}: {e}")