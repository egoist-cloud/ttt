import requests, os, sys, re
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36",
           "Accept": "*/*", "Referer": "https://cs2red.ru"}
CS2RED_COOKIES = {"token": os.getenv("CS2RED_TOKEN",""), "bh": os.getenv("CS2RED_BH",""),
                  "_yasc": os.getenv("CS2RED_YASC",""), "browser_id": os.getenv("CS2RED_BROWSER_ID",""),
                  "yandexuid": os.getenv("CS2RED_YANDEXUID","")}

# скачаем JS и поищем строки с api-рантаймом, включая динамические конкатенации
js = requests.get("https://cs2red.ru/static/index-xN2uZYMy.js", headers=HEADERS, timeout=30).text

# ищем все строковые литералы, похожие на URL-фрагменты с "api"
fragments = set(re.findall(r'["\'`]([^"\'`]*api/[^"\'`]*)["\'`]', js))
print("фрагменты api:")
for f in sorted(fragments):
    print("  ", f)

# ищем ключевые слова времени
print("\nслова time/play/hours:")
for kw in ["timeSeconds","playtime","onlineTime","timeOnServer","totalTime","playedTime","play_time","time_played","game_time","server_time"]:
    n = js.count(kw)
    if n:
        print(f"  {kw}: {n}")
        i = js.find(kw)
        print("    ctx:", js[max(0,i-60):i+80].replace("\n"," "))