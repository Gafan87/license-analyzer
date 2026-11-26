from app import app
with app.app_context():
    import sqlite3
    import os
    from modules.scanner import get_esn_mapping_cached
    from modules.database import get_connection
    
    operator_name = "beeline"
    db_path = "local_licenses.db"
    scan_path = r"D:\_Beeline\_Licenses\_All Licenses"
    
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    
    # Получаем все лицензии beeline
    cursor.execute("SELECT id, filename, lsn, esn FROM licenses WHERE operator = ?", (operator_name,))
    licenses = cursor.fetchall()
    total = len(licenses)
    print(f"Всего лицензий beeline: {total}")
    
    # Строим индекс файлов на диске
    print("Сканируем файлы на диске...")
    file_index = {}
    for root, dirs, files in os.walk(scan_path):
        for f in files:
            if f.lower().endswith(('.xml', '.dat')):
                full_path = os.path.join(root, f)
                file_index[f.lower()] = full_path
    
    print(f"Найдено файлов: {len(file_index)}")
    
    updated = 0
    not_found = 0
    
    for lic_id, filename, lsn, esn in licenses:
        if not filename:
            not_found += 1
            continue
        
        key = filename.lower()
        if key in file_index:
            cursor.execute("UPDATE licenses SET local_path = ? WHERE id = ?", (file_index[key], lic_id))
            updated += 1
        else:
            not_found += 1
    
    conn.commit()
    print(f"\nОбновлено: {updated}")
    print(f"Не найдено: {not_found}")
    
    # Проверка
    cursor.execute("SELECT COUNT(*) FROM licenses WHERE operator = 'beeline' AND local_path IS NOT NULL")
    print(f"beeline с local_path: {cursor.fetchone()[0]}")
    
    conn.close()
    print("\nГотово!")