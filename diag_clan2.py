import requests
import os
import sys
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://cs2red.ru/admin",
    "Origin": "https://cs2red.ru",
}

steam_id = "76561199017448448"
r = requests.get("https://cs2red.ru/api/admin/users",
                 params={"begin": 0, "count": 1, "search": steam_id},
                 cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
j = r.json()
user = (j.get("users") or [None])[0]
if not user:
    print("игрок не найден"); sys.exit()
uid = user.get("id")
print("userId:", uid, "| nick:", user.get("nick"))

r2 = requests.get("https://cs2red.ru/api/clans", cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
data = r2.json()
clans = data.get("clans", [])
print("кланов:", len(clans))

found = None
for clan in clans:
    for m in (clan.get("members") or []):
        if int(m.get("userId")) == uid:
            found = {
                "clan_id": clan.get("id"),
                "clan_name": clan.get("name"),
                "clan_tag": clan.get("tag"),
                "member_role": m.get("roleId"),
                "points": m.get("points"),
            }
            print("найден:", found)
            break
    if found:
        break

if not found:
    print("игрок не состоит ни в одном клане (или клан не подтянулся)")
    # посмотрим структуру одного клана целиком
    if clans:
        import json
        print("\nпример первого клана:")
        c = clans[0]
        print("ключи:", list(c.keys()))
        print("members[:2]:", json.dumps(c.get("members", [])[:2], ensure_ascii=False)[:800])