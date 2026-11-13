# modules/esn_mapper.py
import openpyxl
import os
from modules.logger import get_logger
from modules.database import get_connection, add_change_history
from modules.config_store import get_esn_mapping_config, col_letter_to_index

logger = get_logger(__name__)


def load_esn_mapping_from_excel(file_path):
    """
    Загружает маппинг ESN из Excel файла.
    Колонки берутся из config.json → esn_mapping_config.columns.
    При отсутствии конфига — дефолт A-G (идентично старому поведению).
    """
    if not os.path.exists(file_path):
        logger.warning(f"Файл маппинга не найден: {file_path}")
        return []

    cfg = get_esn_mapping_config()
    cols = cfg.get('columns') or {}
    has_header = cfg.get('has_header', True)

    try:
        idx = {
            'esn':      col_letter_to_index(cols.get('esn', 'A')) - 1,
            'lsn':      col_letter_to_index(cols.get('lsn', 'B')) - 1,
            'operator': col_letter_to_index(cols.get('operator', 'C')) - 1,
            'domain':   col_letter_to_index(cols.get('domain', 'D')) - 1,
            'ne_type':  col_letter_to_index(cols.get('ne_type', 'E')) - 1,
            'city':     col_letter_to_index(cols.get('city', 'F')) - 1,
            'site':     col_letter_to_index(cols.get('site', 'G')) - 1,
        }
    except ValueError as e:
        logger.error(f"Некорректный конфиг колонок ESN-маппинга: {e}")
        return []

    def cell(row, key):
        i = idx[key]
        if i < 0 or i >= len(row):
            return None
        return row[i]

    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb.active

    start_row = 2 if has_header else 1
    mappings = []
    for row in sheet.iter_rows(min_row=start_row, values_only=True):
        esn_raw = cell(row, 'esn')
        if not esn_raw:
            continue
        lsn_raw = cell(row, 'lsn')
        op_raw = cell(row, 'operator')
        dom_raw = cell(row, 'domain')
        ne_raw = cell(row, 'ne_type')
        city_raw = cell(row, 'city')
        site_raw = cell(row, 'site')

        mappings.append({
            'esn': str(esn_raw).strip() if esn_raw else None,
            'lsn': str(lsn_raw).strip() if lsn_raw else None,
            'operator': str(op_raw).strip().lower() if op_raw else None,
            'domain': str(dom_raw).strip() if dom_raw else None,
            'ne_type': str(ne_raw).strip() if ne_raw else None,
            'city': str(city_raw).strip() if city_raw else None,
            'site': str(site_raw).strip() if site_raw else None,
        })

    logger.info(f"Загружено {len(mappings)} записей маппинга из {file_path}")
    return mappings


# ========== НИЖЕ — БЕЗ ИЗМЕНЕНИЙ (save_esn_mapping_to_db, get_mapping_by_esn, ...) ==========

def save_esn_mapping_to_db(mappings, modified_by='system'):
    """Сохраняет маппинг ESN в БД (7 колонок)"""
    conn = get_connection()
    cursor = conn.cursor()

    # Получаем старое количество
    cursor.execute('SELECT COUNT(*) FROM esn_mapping')
    old_count = cursor.fetchone()[0]

    # Удаляем старые записи
    cursor.execute('DELETE FROM esn_mapping')

    added = 0
    for mapping in mappings:
        if mapping.get('esn'):
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO esn_mapping (esn, lsn, operator, domain, ne_type, city, site)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (mapping['esn'], mapping.get('lsn'), mapping.get('operator'),
                      mapping.get('domain'), mapping.get('ne_type'),
                      mapping.get('city'), mapping.get('site')))
                added += 1
            except Exception as e:
                logger.error(f"Ошибка вставки {mapping.get('esn')}: {e}")

    conn.commit()
    conn.close()

    add_change_history('esn_mapping', 0, 'REPLACE', 
                      {'count': old_count}, 
                      {'count': added}, 
                      modified_by)

    return added

def get_mapping_by_esn(esn):
    """Получает маппинг по ESN (с учётом домена)"""
    if not esn:
        return None
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT operator, domain, ne_type, city, site FROM esn_mapping 
        WHERE esn = ? OR esn LIKE ? OR ? LIKE esn
    ''', (esn, f'%{esn}%', esn))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'operator': row[0],
            'domain': row[1],
            'ne_type': row[2],
            'city': row[3],
            'site': row[4]
        }
    return None

def get_mapping_by_lsn(lsn):
    """Получает маппинг по LSN (с учётом домена)"""
    if not lsn:
        return None
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT operator, domain, ne_type, city, site FROM esn_mapping WHERE lsn = ?', (lsn,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'operator': row[0],
            'domain': row[1],
            'ne_type': row[2],
            'city': row[3],
            'site': row[4]
        }
    return None

def export_esn_mapping_to_excel(file_path):
    """Экспортирует маппинг из БД в Excel (7 колонок)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT esn, lsn, operator, domain, ne_type, city, site FROM esn_mapping')
    rows = cursor.fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "ESN Mapping"
    
    # Заголовки (7 колонок)
    headers = ['ESN', 'LSN', 'Оператор', 'Домен', 'NE тип', 'Город', 'Сайт']
    sheet.append(headers)
    
    for row in rows:
        # row теперь кортеж из 7 элементов
        sheet.append(list(row))
    
    # Автоширина колонок
    for col_idx, _ in enumerate(headers, 1):
        max_length = 15
        column_letter = openpyxl.utils.get_column_letter(col_idx)
        for row_idx in range(2, len(rows) + 2):
            cell_value = sheet.cell(row=row_idx, column=col_idx).value
            if cell_value:
                max_length = max(max_length, len(str(cell_value)))
        sheet.column_dimensions[column_letter].width = min(max_length + 2, 40)
    
    wb.save(file_path)
    logger.info(f"Экспортирован маппинг в {file_path}")
