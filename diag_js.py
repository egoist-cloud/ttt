import requests, os, sys, re
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36",
           "Accept": "*/*", "Referer": "https://cs2red.ru", "Origin": "https://cs2red.ru"}
CS2RED_COOKIES = {"token": os.getenv("CS2RED_TOKEN",""), "bh": os.getenv("CS2RED_BH",""),
                  "_yasc": os.getenv("CS2RED_YASC",""), "browser_id": os.getenv("CS2RED_BROWSER_ID",""),
                  "yandexuid": os.getenv("CS2RED_YANDEXUID","")}

steam_id = "76561199017448448"
# страница профиля
html = requests.get(f"https://cs2red.ru/profile/{steam_id}", cookies=CS2RED_COOKIES, headers=HEADERS, timeout=15).text
# найдём js-бандлы
scripts = re.findall(r'src="(/[^"]*\.js[^"]*)"', html)
print("JS бандлы:", scripts[:20])
# также ищем воможные api в html
print("api в html:", sorted(set(re.findall(r'/api/[A-Za-z0-9_\-/\.]*', html)))[:30])
# ищем "time"/"playtime" рядом с api
for m in re.finditer(r'(time|playtime|online.?time|hours)[^"]{0,80}', html, re.I):
    pass