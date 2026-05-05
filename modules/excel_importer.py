import openpyxl
import pandas as pd
from modules.database import save_license
from modules.logger import get_logger

logger = get_logger(__name__)

def import_licenses_from_excel(file_path, operator):
    """Импортирует лицензии из Excel файла"""
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb.active
    
    imported = []
    errors = []
    
    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:  # Пропускаем пустые строки
            continue
        
        try:
            license_data = {
                'operator': operator,
                'lsn': str(row[0]) if row[0] else None,
                'product': str(row[1]) if row[1] else None,
                'version': str(row[2]) if row[2] else None,
                'ne_type': str(row[3]) if row[3] else None,
                'city': str(row[4]) if row[4] else None,
                'site': str(row[5]) if row[5] else None,
                'year': str(row[6]) if row[6] else None,
                'valid_date': str(row[7]) if row[7] else None,
                'create_time': str(row[8]) if row[8] else None,
                'esn': str(row[9]) if row[9] else None,
                'node': str(row[10]) if row[10] else None,
                'resources': [],
                'file_hash': 'imported',
                'filename': f"imported_{row[0]}.xml",
                'last_modified': datetime.now().isoformat(),
                'modified_by': 'import'
            }
            
            # Парсим ресурсы (есть колонки с 11)
            for col_idx in range(11, len(row), 2):
                if col_idx + 1 < len(row):
                    cap_key = row[col_idx]
                    value = row[col_idx + 1]
                    if cap_key and value:
                        license_data['resources'].append({
                            'name': str(cap_key),
                            'value': int(value) if str(value).isdigit() else 0,
                            'valid_date': license_data['valid_date']
                        })
            
            save_license(license_data, 'import')
            imported.append({'row': row_idx, 'lsn': license_data['lsn']})
            
        except Exception as e:
            errors.append({'row': row_idx, 'error': str(e)})
    
    return imported, errors