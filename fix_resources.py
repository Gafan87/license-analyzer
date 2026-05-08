# fix_resources.py
import sqlite3
import json
from modules.database import get_connection

def fix_resources():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем все лицензии с parsed_cache
    cursor.execute('SELECT id, parsed_cache FROM licenses WHERE parsed_cache IS NOT NULL')
    rows = cursor.fetchall()
    
    updated = 0
    for lic_id, cache_json in rows:
        try:
            cache = json.loads(cache_json)
            resources = cache.get('resources', [])
            
            if resources:
                # Удаляем старые ресурсы
                cursor.execute('DELETE FROM resources WHERE license_id = ?', (lic_id,))
                
                # Вставляем новые
                for res in resources:
                    cursor.execute('''
                        INSERT INTO resources (license_id, capacity_key, value, valid_date)
                        VALUES (?, ?, ?, ?)
                    ''', (lic_id, res.get('name'), res.get('value'), res.get('valid_date', 'UNKNOWN')))
                updated += 1
                print(f'Обновлена лицензия {lic_id}: {len(resources)} ресурсов')
        except Exception as e:
            print(f'Ошибка для лицензии {lic_id}: {e}')
    
    conn.commit()
    conn.close()
    print(f'✅ Обновлено {updated} лицензий')

if __name__ == '__main__':
    fix_resources()