import requests
import os
import sys
import json
import time
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

# грузим новые куки динамически — возьмём из .env
links = json.load(open("links.json", encoding="utf-8"))
print("привязанных игроков:", len(links))

# Собираем set всех кланов, к которым относятся привязанные игроки
# Оптимально: один раз скачать /api/clans (там все члены), и искать userId по каждому steamid
# Но чтобы найти userId, нужно steamid->userId через /api/admin/users.

# 1) построим map steamid -> userId
def get_user_id(steam_id):
    try:
        r = requests.get("https://cs2red.ru/api/admin/users",
                         params={"begin": 0, "count": 1, "search": steam_id},
                         cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        j = r.json()
        u = (j.get("users") or [None])[0]
        return u.get("id") if u else None
    except Exception as e:
        print("  err", steam_id, e)
        return None

steam_to_uid = {}
for discord_id, sid in links.items():
    uid = get_user_id(sid)
    steam_to_uid[sid] = uid
    time.sleep(0.3)
    if uid is None:
        print(f"  ⚠️ {sid}: userId не найден")

print("\nuserId по steamid получен. Скачиваем кланы...")
r = requests.get("https://cs2red.ru/api/clans", cookies=CS2RED_COOKIES, headers=HEADERS, timeout=30)
clans = r.json().get("clans", [])
print("всего кланов:", len(clans))

# составить uid -> info
member_clan = {}  # userId -> (clan_id, clan_name, tag, role_in_clan)
for clan in clans:
    cid = clan.get("id")
    cname = clan.get("name")
    ctag = clan.get("tag")
    for m in (clan.get("members") or []):
        uid = m.get("userId")
        member_clan[uid] = (cid, cname, ctag, m.get("roleId"))

# 2) пройти по нашим игрокам
by_clan = {}  # clan_id -> {"name":.., "tag":.., "members":[]}
no_clan = []
not_found = []
for discord_id, sid in links.items():
    uid = steam_to_uid.get(sid)
    if not uid:
        not_found.append(f"{sid}")
        continue
    cl = member_clan.get(uid)
    if cl:
        cid, cname, ctag, crole = cl
        by_clan.setdefault(cid, {"name": cname, "tag": ctag, "members": []})
        by_clan[cid]["members"].append((discord_id, cname))
    else:
        no_clan.append(sid)

print("\n===== КЛАНЫ, ГДЕ СОСТОЯТ ПРИВЯЗАННЫЕ ИГРОКИ =====")
for cid, info in sorted(by_clan.items(), key=lambda x: -len(x[1]["members"])):
    print(f"clan_id={cid}  '{info['name']}' (тег {info['tag']}) — участников: {len(info['members'])}")
print(f"\nБез клана: {len(no_clan)} игроков")
print(f"Игрок не найден (userId None): {len(not_found)} -> {not_found[:10]}")