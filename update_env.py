import re
import os
from dotenv import load_dotenv

load_dotenv()

path = r"C:\Users\kunde\PycharmProjects\WelcomeScreen\.env"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# ВАЖНО: реальные куки из .env не хардкодим — иначе утекут в git.
# Значения читаем из текущего .env. Если хочешь обновить — впиши новые НИЖЕ
# и замени содержимое .env, затем удали этот файл из git (см. комментарий в конце).
token = os.getenv("CS2RED_TOKEN", "")
bh = os.getenv("CS2RED_BH", "")
yasc = os.getenv("CS2RED_YASC", "")
browser_id = os.getenv("CS2RED_BROWSER_ID", "")
yandexuid = os.getenv("CS2RED_YANDEXUID", "")

repl = {
    "CS2RED_TOKEN": token,
    "CS2RED_BH": bh,
    "CS2RED_YASC": yasc,
    "CS2RED_BROWSER_ID": browser_id,
    "CS2RED_YANDEXUID": yandexuid,
}

for key, val in repl.items():
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f"{key}={val}", content)
    else:
        content += f"\n{key}={val}\n"

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("OK: cookie values updated in .env")