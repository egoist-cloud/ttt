import requests, os, sys, json
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Referer": "https://cs2red.ru"}
CS2RED_COOKIES = {"token": os.getenv("CS2RED_TOKEN",""), "bh": os.getenv("CS2RED_BH",""),
                  "_yasc": os.getenv("CS2RED_YASC",""), "browser_id": os.getenv("CS2RED_BROWSER_ID",""),
                  "yandexuid": os.getenv("CS2RED_YANDEXUID","")}

steam_id = "76561199017448448"

# 1) большая пагинация stats ищем поле времени
for pn in [0, 1]:
    r = requests.get("https://cs2red.ru/api/data/stats",
                     params={"begin": pn*50, "count": 50}, cookies=CS2RED_COOKIES, headers=HEADERS, timeout=20)
    j = r.json()
    st = j.get("stats", [])
    print(f"page {pn}: {len(st)}")
    if st:
        print("ключи:", list(st[0].keys()))
        # есть ли вложенные объекты с временем
        s = st[0]
        for k,v in s.items():
            if isinstance(v, dict):
                print("  dict поле", k, "->", list(v.keys())[:15])

# 2) profile страница есть ли API в другом бандле. Скачаем саму страницу и найдём main.js
html = requests.get(f"https://cs2red.ru/profile/{steam_id}", cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15).text
import re
scripts = re.findall(r'src="(/static/[^"]+\.js)"', html)
print("\nscripts:", scripts)
for s in scripts:
    js = requests.get("https://cs2red.ru"+s, headers=HEADERS, timeout=30).text
    print(f"--- {s} len={len(js)} ---")
    for kw in ["playtime","onlineTime","timeOnServer","time","servers","game_time"]:
        c = js.count(kw)
        if c:
            print(f"   {kw}: {c}")
    # найду api фрагменты
    for frag in sorted(set(re.findall(r'["\'`]([^"\'`]*api/[^"\'`]*)["\'`]', js))):
        print("   api:", frag)