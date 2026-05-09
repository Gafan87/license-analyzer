# fill_license_domain.py
from modules.database import get_connection
from modules.esn_mapper import get_mapping_by_esn

conn = get_connection()
cursor = conn.cursor()

# Получаем все лицензии с ESN, у которых domain пустой
cursor.execute('SELECT id, esn FROM licenses WHERE esn IS NOT NULL AND esn != "" AND (domain IS NULL OR domain = "")')
rows = cursor.fetchall()

updated = 0
for lic_id, esn in rows:
    mapping = get_mapping_by_esn(esn)
    if mapping and mapping.get('domain'):
        cursor.execute('UPDATE licenses SET domain = ? WHERE id = ?', (mapping['domain'], lic_id))
        updated += 1
        print(f'Обновлена лицензия {lic_id}: domain={mapping["domain"]}')

conn.commit()
conn.close()
print(f'✅ Обновлено {updated} лицензий')