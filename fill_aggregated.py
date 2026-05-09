# fill_aggregated.py
import sys
sys.path.insert(0, 'D:\\MyDocs\\License management')
import sqlite3
import json
from modules.database import get_connection

def fill_aggregated():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, parsed_cache FROM licenses WHERE parsed_cache IS NOT NULL')
    rows = cursor.fetchall()
    
    updated = 0
    for lic_id, cache_json in rows:
        try:
            cache = json.loads(cache_json)
            resources = cache.get('resources', [])
            
            for res in resources:
                cursor.execute('''
                    INSERT OR REPLACE INTO capacity_aggregated 
                    (license_id, capacity_key, total_value, permanent_value, dated_values, latest_date, latest_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lic_id,
                    res.get('name'),
                    res.get('total_value', res.get('value', 0)),
                    res.get('permanent_value', 0),
                    res.get('dated_values', '[]'),
                    res.get('latest_date'),
                    res.get('latest_value', 0)
                ))
            updated += 1
            if updated % 100 == 0:
                print(f'Обработано {updated} лицензий...')
        except Exception as e:
            print(f'Ошибка для лицензии {lic_id}: {e}')
    
    conn.commit()
    conn.close()
    print(f'✅ Готово! Обновлено {updated} лицензий')

if __name__ == '__main__':
    fill_aggregated()