import requests, os, sys, re
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/154.0.0.0 Safari/537.36", "Accept": "*/*",
           "Referer": "https://cs2red.ru"}
js = requests.get("https://cs2red.ru/static/index-xN2uZYMy.js", headers=HEADERS, timeout=30).text
print("размер JS:", len(js))
# ищем строки с api и временем
# все /api/... пути
apis = sorted(set(re.findall(r'"/api/[^"]*"', js)))
print("api-пути в JS:")
for a in apis:
    if any(k in a for k in ["time","play","stat","online","vip","service","user","profile"]):
        print("  ", a)
print("\n--- поиск слов playtime/time ---")
for m in re.finditer(r'([a-zA-Z0-9_/\.\-]{0,40}(?:playtime|timePlayed|onlineTime|time_played|play_time|hours)[a-zA-Z0-9_/\.\-]{0,40})', js, re.I):
    print("  ", m.group(1))