import sqlite3
import json

conn = sqlite3.connect('local_licenses.db')
cur = conn.cursor()
cur.execute('SELECT parsed_cache FROM licenses WHERE id = 3764')
row = cur.fetchone()
conn.close()

if row and row[0]:
    cache = json.loads(row[0])
    spart_hierarchy = cache.get('spart_hierarchy', {})
    sparts = spart_hierarchy.get('sparts', [])
    print('SParts в parsed_cache:', len(sparts))
    if sparts:
        print('Первый SPart:', sparts[0].get('name'))
        print('  bparts:', len(sparts[0].get('bparts', [])))
        bpart_names = [b.get('name') for b in sparts[0].get('bparts', [])][:5]
        print('  bpart names:', bpart_names)
else:
    print('Нет parsed_cache')