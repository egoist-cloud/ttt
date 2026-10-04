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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://cs2red.ru", "Origin": "https://cs2red.ru",
}

steam_id = "76561199017448448"
uid = 135587

# 1) полный ответ api/services с userId — ищем, есть ли купленные услуги
r = requests.get("https://cs2red.ru/api/services", params={"userId": uid},
                 cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
print("=== api/services (полный) ===")
j = r.json()
print("ключи:", list(j.keys()))
srv = j.get("services", [])
if srv:
    print("сервисов:", len(srv))
    print("ключи сервиса:", list(srv[0].keys()))
    # есть ли где-то купленные?
print(json.dumps(j, ensure_ascii=False)[:2500])

# 2) публичный профиль — посмотреть, какие API он вызывает
print("\n=== профиль страница ===")
pu = f"https://cs2red.ru/profile/{steam_id}"
try:
    rr = requests.get(pu, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15)
    print("status:", rr.status_code)
    html = rr.text
    # поищем api-вызовы в html
    import re as _re
    apis = sorted(set(_re.findall(r'/api/[a-zA-Z0-9_/\-\.\?\=\{\}]*', html)))
    print("api в html:", apis[:40])
    # поищем "playtime" / "time" подсказки
    for kw in ["playtime", "timeOnline", "onlineTime", "hours", "play_time", "time_played"]:
        if kw in html:
            idx = html.find(kw)
            print(f"найдено '{kw}':", html[max(0,idx-120):idx+120].replace("\n"," ")[:220])
except Exception as e:
    print("EXC profile:", e)

# 3) эндпоинты купленных услуг
print("\n=== покупки/услуги пользователя ===")
for ep in [
    f"https://cs2red.ru/api/user/services?userId={uid}",
    f"https://cs2red.ru/api/user/{uid}/services",
    f"https://cs2red.ru/api/data/purchases?userId={uid}",
    f"https://cs2red.ru/api/data/payments?userId={uid}",
    f"https://cs2red.ru/api/data/user-services?userId={uid}",
    f"https://cs2red.ru/api/data/services/user/{uid}",
    f"https://cs2red.ru/api/services/user/{uid}",
]:
    try:
        rr = requests.get(ep, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=10)
        print(f"{rr.status_code} {ep} -> {rr.text[:180]}")
    except Exception as e:
        print(f"EXC {ep}: {e}")