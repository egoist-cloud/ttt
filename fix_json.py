import json, re

FILES = ["links.json", "mass_links.json"]

def repair_text(raw):
    # Заменяем: конец строки с "..." за которым идёт строка с "ключ": на ","
    fixed = re.sub(r'(")\s*\n(\s*")', r'",\n\2', raw)
    # убираем лишние запятые перед закрывающей }
    fixed = re.sub(r',\s*}', '}', fixed)
    return fixed

for path in FILES:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(repair_text(raw))
    except Exception as e:
        print(f"!!! {path}: {e}")
        continue
    if not isinstance(data, dict):
        print(f"!!! {path}: не объект")
        continue
    cleaned = {}
    for k, v in data.items():
        vs = str(v).strip()
        if vs.isdigit() and len(vs) == 17:
            cleaned.setdefault(k, vs)
    # сохраняем НОВЫЙ файл (не трогаем .bak)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    print(f"{path}: отремонтировано, записей {len(cleaned)}")