from app import app
with app.app_context():
    import sqlite3
    import json
    from datetime import datetime
    import os
    import traceback
    
    from modules.parser_dat import parse_dat_license
    from modules.parser_xml import parse_xml_license
    from modules.scanner import get_esn_mapping_cached, get_file_hash
    from modules.database import get_license_by_id
    
    operator_name = "beeline"
    db_path = "local_licenses.db"
    
    def quick_save(license_data):
        """Быстрое сохранение в БД напрямую"""
        conn = sqlite3.connect(db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Проверяем существующую
        cursor.execute('''
            SELECT id FROM licenses 
            WHERE operator = ? AND ne_type = ? AND city = ? AND site = ? AND year = ? AND lsn = ?
        ''', (license_data['operator'], license_data['ne_type'], license_data['city'], 
              license_data['site'], license_data.get('year'), license_data['lsn']))
        existing = cursor.fetchone()
        
        if existing:
            lic_id = existing[0]
            cursor.execute('''
                UPDATE licenses SET
                    filename=?, file_hash=?, product=?, version=?, esn=?, node=?,
                    create_time=?, valid_date=?, domain=?, local_path=?,
                    last_modified=?, modified_by=?
                WHERE id=?
            ''', (
                license_data.get('filename'), license_data.get('file_hash'),
                license_data.get('product'), license_data.get('version'),
                license_data.get('esn'), license_data.get('node'),
                license_data.get('create_time'), license_data.get('valid_date'),
                license_data.get('domain'), license_data.get('local_path'),
                now, 'test', lic_id
            ))
        else:
            cursor.execute('''
                INSERT INTO licenses (
                    operator, ne_type, city, site, year, filename, file_hash,
                    lsn, product, version, esn, node, create_time, valid_date,
                    domain, local_path, last_modified, modified_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                license_data['operator'], license_data['ne_type'], license_data['city'],
                license_data['site'], license_data.get('year'),
                license_data.get('filename'), license_data.get('file_hash'),
                license_data['lsn'], license_data.get('product'), license_data.get('version'),
                license_data.get('esn'), license_data.get('node'),
                license_data.get('create_time'), license_data.get('valid_date'),
                license_data.get('domain'), license_data.get('local_path'),
                now, 'test'
            ))
            lic_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        return lic_id
    
    # ========== ТЕСТ 1: DAT ==========
    print("=" * 60)
    print("ТЕСТ 1: DAT лицензия")
    
    file_path_1 = r"D:\_Beeline\_Licenses\_All Licenses\IMS_CORE\RST_IMS\2028-03-01\LICCloudATS9900_RST_IMS_2027.dat"
    license_data_1 = parse_dat_license(file_path_1)
    
    all_mappings = get_esn_mapping_cached(operator_name)
    mapping_1 = None
    for m in all_mappings:
        if m.get('esn') == license_data_1.get('esn') or m.get('lsn') == license_data_1.get('lsn'):
            mapping_1 = m
            break
    
    result_1 = {
        'operator': operator_name,
        'ne_type': mapping_1.get('ne_type') if mapping_1 else 'CloudATS9900',
        'city': mapping_1.get('city') if mapping_1 else 'RST',
        'site': mapping_1.get('site') if mapping_1 else 'IMS',
        'domain': mapping_1.get('domain') if mapping_1 else None,
        'filename': os.path.basename(file_path_1),
        'file_hash': get_file_hash(file_path_1),
        'lsn': license_data_1.get('lsn'),
        'product': license_data_1.get('product'),
        'version': license_data_1.get('version'),
        'esn': license_data_1.get('esn'),
        'node': license_data_1.get('node'),
        'create_time': license_data_1.get('create_time'),
        'valid_date': license_data_1.get('valid_date'),
        'local_path': file_path_1,
        'year': None
    }
    
    try:
        lic_id_1 = quick_save(result_1)
        print(f"✅ DAT сохранён! ID = {lic_id_1}")
        saved_1 = get_license_by_id(lic_id_1)
        print(f"  local_path: {saved_1.get('local_path')}")
        print(f"  domain: {saved_1.get('domain')}")
    except Exception as e:
        print(f"❌ Ошибка DAT: {e}")
        traceback.print_exc()
    
    # ========== ТЕСТ 2: XML ==========
    print("\n" + "=" * 60)
    print("ТЕСТ 2: XML лицензия")
    
    file_path_2 = r"D:\_Beeline\_Licenses\_All Licenses\vEPC_CORE\VLD\2028-03-01\LICUNC(MME)_VLD_vEPC2_2027.xml"
    license_data_2 = parse_xml_license(file_path_2)
    
    mapping_2 = None
    for m in all_mappings:
        if m.get('esn') == license_data_2.get('esn') or m.get('lsn') == license_data_2.get('lsn'):
            mapping_2 = m
            break
    
    result_2 = {
        'operator': operator_name,
        'ne_type': mapping_2.get('ne_type') if mapping_2 else 'unknown',
        'city': mapping_2.get('city') if mapping_2 else 'unknown',
        'site': mapping_2.get('site') if mapping_2 else 'unknown',
        'domain': mapping_2.get('domain') if mapping_2 else None,
        'filename': os.path.basename(file_path_2),
        'file_hash': get_file_hash(file_path_2),
        'lsn': license_data_2.get('lsn'),
        'product': license_data_2.get('product'),
        'version': license_data_2.get('version'),
        'esn': license_data_2.get('esn'),
        'node': license_data_2.get('node'),
        'create_time': license_data_2.get('create_time'),
        'valid_date': license_data_2.get('valid_date'),
        'local_path': file_path_2,
        'year': None
    }
    
    try:
        lic_id_2 = quick_save(result_2)
        print(f"✅ XML сохранён! ID = {lic_id_2}")
        saved_2 = get_license_by_id(lic_id_2)
        print(f"  local_path: {saved_2.get('local_path')}")
        print(f"  domain: {saved_2.get('domain')}")
    except Exception as e:
        print(f"❌ Ошибка XML: {e}")
        traceback.print_exc()
    
    print("\nТЕСТЫ ЗАВЕРШЕНЫ")