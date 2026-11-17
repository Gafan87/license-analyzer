import re, os, sys, traceback

os.chdir(r"D:\MyDocs\License management")
path = "modules/bulk_reorganizer.py"

try:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    in_preview = False
    patched = False
    var_name = "row"
    
    for i, line in enumerate(lines):
        if "def preview(" in line:
            in_preview = True
        
        # Ищем, где бэкенд формирует словарь (по ключу 'lsn')
        if in_preview and "'lsn':" in line:
            # Проверяем, нет ли уже там ключа domain
            if any("'domain':" in l for l in lines[max(0, i-5):min(len(lines), i+5)]):
                print("Поле 'domain' уже передается в бэкенде.")
                patched = True
                break
            
            # Находим имя переменной (row, lic_data и т.д.), из которой читаются данные
            m = re.search(r"['\"]lsn['\"]\s*:\s*([a-zA-Z0-9_]+)", line)
            if m:
                var_name = m.group(1)
            
            # Вставляем передачу домена прямо под 'lsn'
            indent = line[:len(line) - len(line.lstrip())]
            lines.insert(i + 1, f"{indent}'domain': {var_name}.get('domain') or 'default',\n")
            patched = True
            break

    if patched:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Бэкенд успешно обновлен! Поле 'domain' (через {var_name}) теперь передается в UI.")
    else:
        print("Внимание: Не удалось найти место для вставки. Нужна ручная диагностика.")

except Exception as e:
    traceback.print_exc()
    sys.exit(1)