# check_capacity_aggregated.py
import sys
sys.path.insert(0, 'D:\\MyDocs\\License management')
import sqlite3

conn = sqlite3.connect('local_licenses.db')
cur = conn.cursor()

# Найдем ID последней добавленной лицензии
cur.execute('SELECT id, lsn, filename FROM licenses ORDER BY id DESC LIMIT 1')
row = cur.fetchone()
if row:
    lic_id, lsn, filename = row
    print(f'Последняя лицензия: ID={lic_id}, LSN={lsn}, файл={filename}')
    
    # Проверим capacity_aggregated для этой лицензии
    cur.execute('SELECT capacity_key, total_value, permanent_value, latest_value, latest_date FROM capacity_aggregated WHERE license_id=?', (lic_id,))
    rows = cur.fetchall()
    print(f'\ncapacity_aggregated для ID={lic_id}:')
    for r in rows[:10]:
        print(f'  {r[0]}: total={r[1]}, perm={r[2]}, latest={r[3]} ({r[4]})')
else:
    print('Нет лицензий в БД')

conn.close()