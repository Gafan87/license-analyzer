import sys
sys.path.insert(0, 'D:\\MyDocs\\License management')

from modules.parser_xml import parse_xml_license
from modules.database import get_connection
import json

conn = get_connection()
cur = conn.cursor()

# Получаем filename лицензии 3764
cur.execute('SELECT filename FROM licenses WHERE id = 3764')
row = cur.fetchone()
filename = row[0] if row else None

print(f'Filename: {filename}')

# Нужно найти полный путь к файлу. 
# Он хранится в parsed_cache или нужно знать базовую папку.
# Попробуем получить из parsed_cache
cur.execute('SELECT parsed_cache FROM licenses WHERE id = 3764')
row2 = cur.fetchone()
if row2 and row2[0]:
    cache = json.loads(row2[0])
    path = cache.get('file_path')
    print(f'Путь из parsed_cache: {path}')
else:
    # Если нет, нужно указать путь вручную или искать по имени
    # Примерный путь (замени на реальный)
    path = r'D:\_Beeline\_Licenses\_All Licenses\vEPC_CORE\NSK\2028-03-01\LICUDG_NSK_vEPC1_2027.xml'
    print(f'Используем путь по умолчанию: {path}')

if path:
    data = parse_xml_license(path)
    if data:
        # Обновляем parsed_cache
        cur.execute('UPDATE licenses SET parsed_cache = ? WHERE id = 3764', (json.dumps(data['parsed_cache']),))
        
        # Удаляем старые данные
        cur.execute('DELETE FROM resources WHERE license_id = 3764')
        cur.execute('DELETE FROM capacity_aggregated WHERE license_id = 3764')
        cur.execute('DELETE FROM license_spart_hierarchy WHERE license_id = 3764')
        cur.execute('DELETE FROM license_bpart_hierarchy WHERE license_id = 3764')
        
        # Сохраняем ресурсы
        for res in data.get('resources', []):
            cur.execute('''
                INSERT INTO resources (license_id, capacity_key, value, valid_date)
                VALUES (?, ?, ?, ?)
            ''', (3764, res.get('name'), res.get('value', 0), res.get('valid_date', 'UNKNOWN')))
            
            cur.execute('''
                INSERT INTO capacity_aggregated 
                (license_id, capacity_key, total_value, permanent_value, dated_values, latest_date, latest_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (3764, res.get('name'), res.get('total_value', 0), res.get('permanent_value', 0),
                  res.get('dated_values', '[]'), res.get('latest_date'), res.get('latest_value', 0)))
        
        # Сохраняем иерархию
        hierarchy = data.get('spart_hierarchy', {})
        for spart in hierarchy.get('sparts', []):
            cur.execute('''
                INSERT INTO license_spart_hierarchy (license_id, spart_name, spart_value, spart_valid_date)
                VALUES (?, ?, ?, ?)
            ''', (3764, spart.get('name'), spart.get('value', 0), spart.get('valid_date', 'UNKNOWN')))
            spart_id = cur.lastrowid
            
            for bpart in spart.get('bparts', []):
                cur.execute('''
                    INSERT INTO license_bpart_hierarchy (license_id, spart_id, bpart_name, bpart_value, bpart_valid_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (3764, spart_id, bpart.get('name'), bpart.get('value', 0), bpart.get('valid_date', 'UNKNOWN')))
        
        conn.commit()
        print('Лицензия 3764 обновлена')
    else:
        print('Ошибка парсинга')
else:
    print('Путь не найден')

conn.close()