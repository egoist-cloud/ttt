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

# известный игрок из прошлого ответа. Найди по его steamid64 → id
steam_id = "76561199017448448"

# 1) ищем игрока, чтобы получить его id
r = requests.get("https://cs2red.ru/api/admin/users",
                 params={"begin": 0, "count": 1, "search": steam_id},
                 cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
print("SEARCH статус:", r.status_code)
j = r.json()
user = (j.get("users") or [None])[0]
if not user:
    print("игрок не найден")
    sys.exit()
uid = user.get("id")
print("user id:", uid, "| nick:", user.get("nick"), "| roleId:", user.get("roleId"))

# 2) пробуем полный профиль по id
for path in [
    f"https://cs2red.ru/api/admin/user?userId={uid}",
    f"https://cs2red.ru/api/admin/user/{uid}",
    f"https://cs2red.ru/api/user/{uid}",
]:
    try:
        rr = requests.get(path, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
        print(f"\nGET {path}\n  -> {rr.status_code}: {rr.text[:1200]}")
    except Exception as e:
        print(f"GET {path} EXC: {e}")

# 3) попробуем эндпоинт кланов
for path in [
    "https://cs2red.ru/api/clans",
    "https://cs2red.ru/api/data/clans",
]:
    try:
        rr = requests.get(path, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
        print(f"\nGET {path}\n  -> {rr.status_code}: {rr.text[:600]}")
    except Exception as e:
        print(f"GET {path} EXC: {e}")