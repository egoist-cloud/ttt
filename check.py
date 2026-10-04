import json, os
print("Каталог:", os.getcwd())
for f in ["links.json", "mass_links.json", "users_db.json", "players_db.json"]:
    p = os.path.join(os.getcwd(), f)
    if not os.path.exists(p):
        print(f"❌ {f}: файла НЕТ в этом каталоге")
        continue
    size = os.path.getsize(p)
    print(f"📄 {f}: размер {size} байт")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        print(f"   ✅ валидный JSON, записей: {len(data)}")
    except Exception as e:
        print(f"   ❌ ОШИБКА JSON: {e}")