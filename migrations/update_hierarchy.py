# migrations/update_hierarchy.py
"""
Скрипт для обновления существующих XML лицензий — извлечение иерархии SPart/BPart
Запуск: python migrations/update_hierarchy.py
"""

import sys
import os
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.database import get_connection
from modules.parser_xml import parse_xml_license

def update_hierarchy():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Проверяем, какие колонки есть в таблице licenses
    cursor.execute("PRAGMA table_info(licenses)")
    columns = [c[1] for c in cursor.fetchall()]
    print(f"Колонки в licenses: {columns}")
    
    # Получаем все XML лицензии (по расширению filename)
    # У нас нет колонки file_type, определяем по расширению файла
    cursor.execute('''
        SELECT id, filename, parsed_cache 
        FROM licenses 
        WHERE filename LIKE '%.xml' OR filename LIKE '%.XML'
    ''')
    rows = cursor.fetchall()
    
    updated = 0
    errors = 0
    
    for lic_id, filename, cache_json in rows:
        try:
            # Проверяем, есть ли уже иерархия в parsed_cache
            if cache_json:
                cache = json.loads(cache_json)
                if 'spart_hierarchy' in cache and cache['spart_hierarchy'].get('sparts'):
                    # Иерархия уже есть, пропускаем
                    print(f'Иерархия уже есть для лицензии {lic_id}, пропускаем')
                    continue
            
            # Если нет иерархии, нужно перепарсить файл
            # Но у нас нет local_path, нужно найти файл
            # Пропускаем для сейчас, потом доработаем
            print(f'Для лицензии {lic_id} нет иерархии, нужно пересканирование')
            updated += 1
            
        except Exception as e:
            errors += 1
            print(f'Ошибка для лицензии {lic_id}: {e}')
    
    conn.commit()
    conn.close()
    print(f'✅ Проверено {len(rows)} XML лицензий, ошибок {errors}')
    print('⚠️ Для полного обновления иерархии требуется пересканирование всех XML файлов')

if __name__ == '__main__':
    update_hierarchy()