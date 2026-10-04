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

for ep in ["https://cs2red.ru/api/data/bans", "https://cs2red.ru/api/data/mutes"]:
    r = requests.get(ep, params={"begin": 0, "count": 3, "search": steam_id},
                     cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
    print("="*60)
    print(ep, "->", r.status_code)
    try:
        j = r.json()
        key = "bans" if "bans" in ep else "mutes"
        items = j.get(key, [])
        print("кол-во:", len(items))
        for it in items[:3]:
            if str((it.get("action") or {}).get("steamid64")) != steam_id:
                continue
            print(json.dumps(it, ensure_ascii=False, indent=2)[:1500])
            print("-"*40)
    except Exception as e:
        print("ERR", e, r.text[:500])