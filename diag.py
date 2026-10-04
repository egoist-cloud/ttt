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

CS2RED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.6",
    "Referer": "https://cs2red.ru/admin",
    "Origin": "https://cs2red.ru",
}

steam_id = "76561199017448448"
url = "https://cs2red.ru/api/admin/users"

for search_val in (steam_id, "76561199017448448"):
    url_candidates = [
        url + "?" + "&".join([f"begin=0", f"count=1", f"search={search_val}"]),
    ]
    break

try:
    r = requests.get(
        url,
        params={"begin": 0, "count": 1, "search": steam_id},
        cookies=CS2RED_COOKIES,
        headers=CS2RED_HEADERS,
        timeout=15,
    )
    print("HTTP статус:", r.status_code)
    print("Тело ответа (первые 800 символов):")
    print(r.text[:800])
except Exception as e:
    print("Исключение:", type(e).__name__, e)