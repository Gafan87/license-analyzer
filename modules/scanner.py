import os
import hashlib
from modules.parser_xml import parse_xml_license, extract_year_from_valid_date
from modules.parser_dat import parse_dat_license
from modules.esn_mapper import get_mapping_by_esn, get_mapping_by_lsn
from modules.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)

# Глобальный кэш маппинга
_mapping_cache = None
_mapping_cache_time = 0

def get_esn_mapping_cached(operator_name):
    """
    Загружает маппинг ESN для конкретного оператора
    """
    global _mapping_cache, _mapping_cache_time
    import time
    from modules.esn_mapper import load_esn_mapping_from_excel
    from flask import current_app
    
    cache_key = f'mapping_{operator_name}'
    
    if _mapping_cache is not None and (time.time() - _mapping_cache_time) < 60:
        return _mapping_cache
    
    # Получаем конфиг оператора
    operators = current_app.config.get('OPERATORS', [])
    op_config = None
    for op in operators:
        if op.get('name') == operator_name:
            op_config = op
            break
    
    if not op_config:
        return []
    
    mapping_filename = op_config.get('mapping_file', f'{operator_name}_esn_mapping.xlsx')
    mapping_path = current_app.config.get('mapping_path', '//A00742028-C5NC5/_Licenses/mapping')
    mapping_file = os.path.join(mapping_path, mapping_filename)
    
    if os.path.exists(mapping_file):
        _mapping_cache = load_esn_mapping_from_excel(mapping_file)
        _mapping_cache_time = time.time()
        logger.info(f"Загружен маппинг для {operator_name} из {mapping_file}: {len(_mapping_cache)} записей")
    else:
        logger.warning(f"Файл маппинга для {operator_name} не найден: {mapping_file}")
        _mapping_cache = []
    
    return _mapping_cache

def get_file_hash(filepath):
    """Вычисляет MD5 хеш файла"""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

def extract_from_filename(filename):
    """Извлекает информацию из имени файла"""
    # Формат: {product}_{version}_{city}_{site}_{year}.xml
    import re
    result = {'product': None, 'version': None, 'city': None, 'site': None, 'year': None}
    
    # Пробуем извлечь информацию
    parts = filename.replace('.xml', '').replace('.dat', '').split('_')
    
    if len(parts) >= 5:
        result['product'] = parts[0]
        result['version'] = parts[1]
        result['city'] = parts[2]
        result['site'] = parts[3]
        result['year'] = parts[4]
    elif len(parts) >= 4:
        result['product'] = parts[0]
        result['version'] = parts[1]
        result['city'] = parts[2]
        result['site'] = parts[3]
    
    return result

def scan_local_folder(local_path, operator_name):
    """
    Сканирует локальную папку и возвращает список найденных лицензий
    """
    if not os.path.exists(local_path):
        logger.warning(f"Путь не существует: {local_path}")
        return []

    licenses = []

    for root, dirs, files in os.walk(local_path):
        for filename in files:
            if not (filename.lower().endswith('.xml') or filename.lower().endswith('.dat')):
                continue

            file_path = os.path.join(root, filename)
            logger.info(f"Сканирование: {file_path}")

            # Парсим файл
            if filename.lower().endswith('.xml'):
                license_data = parse_xml_license(file_path)
            else:
                license_data = parse_dat_license(file_path)

            if not license_data:
                logger.warning(f"Не удалось распарсить: {filename}")
                continue

            # Получаем ESN и LSN
            esn = license_data.get('esn')
            lsn = license_data.get('lsn')

            # Ищем маппинг (сначала в загруженном файле, потом в БД)
            mapping = None
            domain = None
            
            # 1. Пробуем найти в загруженном Excel файле
            all_mappings = get_esn_mapping_cached(operator_name)
            for m in all_mappings:
                if m.get('esn') == esn:
                    mapping = m
                    domain = m.get('domain')
                    break
                if m.get('lsn') == lsn:
                    mapping = m
                    domain = m.get('domain')
                    break
            
            # 2. Если не нашли, пробуем в БД
            if not mapping:
                if esn:
                    mapping = get_mapping_by_esn(esn)
                    if mapping:
                        domain = mapping.get('domain')
                if not mapping and lsn:
                    mapping = get_mapping_by_lsn(lsn)
                    if mapping:
                        domain = mapping.get('domain')

            # Извлекаем информацию из имени файла
            file_info = extract_from_filename(filename)

            # Определяем метаданные (приоритет: маппинг > имя файла > путь)
            operator = mapping.get('operator') if mapping else operator_name
            ne_type = mapping.get('ne_type') if mapping else file_info.get('product')
            city = mapping.get('city') if mapping else file_info.get('city')
            site = mapping.get('site') if mapping else file_info.get('site')

            # Год действия из validDate
            valid_date = license_data.get('valid_date', 'UNKNOWN')
            year_folder = extract_year_from_valid_date(valid_date)

            # Если год не определён, пробуем из имени файла
            if year_folder == 'unknown' and file_info.get('year'):
                year_folder = file_info['year']

            # Формируем результат
            result = {
                'operator': operator,
                'ne_type': ne_type or 'unknown',
                'city': city or 'unknown',
                'site': site or 'unknown',
                'year': year_folder if year_folder != 'unknown' else None,
                'filename': filename,
                'file_hash': get_file_hash(file_path),
                'lsn': lsn,
                'product': license_data.get('product'),
                'version': license_data.get('version'),
                'esn': esn,
                'node': license_data.get('node'),
                'create_time': license_data.get('create_time'),
                'valid_date': valid_date,
                'resources': license_data.get('resources', []),
                'aggregated_resources': license_data.get('resources', []),
                'local_path': file_path,
                'domain': domain  # ← ДОБАВЛЯЕМ DOMAIN СРАЗУ
            }

            # Добавляем parsed_cache если есть
            if 'parsed_cache' in license_data:
                result['parsed_cache'] = license_data['parsed_cache']

            licenses.append(result)
            logger.debug(f"Обработано: {filename} -> {operator}/{ne_type}/{city}/{site}/{year_folder} (domain={domain})")

    return licenses

def extract_tags_from_path(file_path, root_path):
    """Извлекает теги из пути файла"""
    import os
    rel_path = os.path.relpath(file_path, root_path)
    parts = rel_path.split(os.sep)
    
    tags = {}
    if len(parts) >= 1:
        tags['ne_type'] = parts[0]
    if len(parts) >= 2:
        tags['city'] = parts[1]
    if len(parts) >= 3:
        tags['site'] = parts[2]
    if len(parts) >= 4:
        year_part = parts[3]
        tags['year'] = year_part if year_part.isdigit() else None
    
    return tags

# ========== ДИНАМИЧЕСКИЕ ПОЛЯ ==========

def extract_dynamic_values_from_license(license_data, extraction_rules):
    """
    Извлекает значения динамических полей из данных лицензии
    license_data: результат парсинга (содержит lsn, esn, resources и т.д.)
    extraction_rules: словарь правил из extraction_rules.json
    """
    import re
    
    results = {}
    
    for rule_id, rule in extraction_rules.get('rules', {}).items():
        value = None
        
        # Для фичей (CapacityKey)
        if rule.get('is_capacity_key'):
            capacity_key = rule.get('capacity_key')
            if capacity_key and license_data.get('resources'):
                # Суммируем значения фичи (только активные)
                total = 0
                today = datetime.now().date()
                for res in license_data['resources']:
                    if res['name'] == capacity_key:
                        valid_date = res.get('valid_date', '')
                        if valid_date == 'PERMANENT':
                            total += int(res['value'])
                        elif valid_date and valid_date != 'UNKNOWN':
                            try:
                                date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d').date()
                                if date_obj >= today:
                                    total += int(res['value'])
                            except:
                                total += int(res['value'])
                if total > 0:
                    value = str(total)
        
        # Для обычных полей с XPath (для XML)
        elif license_data.get('file_type') == 'xml' and rule.get('xpath_xml'):
            # Парсим XML если нужно
            if 'parsed_xml' not in license_data and license_data.get('raw_content'):
                try:
                    import xml.etree.ElementTree as ET
                    license_data['parsed_xml'] = ET.fromstring(license_data['raw_content'])
                except:
                    pass
            
            if license_data.get('parsed_xml'):
                try:
                    elements = license_data['parsed_xml'].findall(rule['xpath_xml'])
                    if elements:
                        values = [e.text for e in elements if e.text]
                        if values:
                            strategy = rule.get('aggregation_strategy', 'first')
                            if strategy == 'first':
                                value = values[0]
                            elif strategy == 'last':
                                value = values[-1]
                            elif strategy == 'join':
                                separator = rule.get('join_separator', ', ')
                                value = separator.join(values)
                except Exception as e:
                    pass
        
        # Для обычных полей с Regex (для DAT)
        elif license_data.get('file_type') == 'dat' and rule.get('regex_dat'):
            content = license_data.get('raw_content', '')
            if content:
                try:
                    # Убираем 'r' из начала строки если есть
                    pattern = rule['regex_dat']
                    if pattern.startswith('r"') and pattern.endswith('"'):
                        pattern = pattern[2:-1]
                    elif pattern.startswith("r'") and pattern.endswith("'"):
                        pattern = pattern[2:-1]
                    
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        value = match.group(1) if match.groups() else match.group(0)
                except Exception as e:
                    pass
        
        if value:
            results[rule_id] = value
    
    return results


def update_dynamic_values_for_all_licenses(operator, extraction_rules, column_id=None, column_config=None):
    """
    Обновляет динамические значения для всех лицензий оператора
    Используется при добавлении новой колонки
    """
    from modules.database import get_connection, set_dynamic_value, get_dynamic_columns
    import os
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем все лицензии оператора
    cursor.execute('SELECT id, filename, local_path FROM licenses WHERE operator = ?', (operator,))
    licenses = cursor.fetchall()
    conn.close()
    
    updated = 0
    errors = 0
    
    for lic_id, filename, local_path in licenses:
        try:
            # Парсим файл
            if local_path and os.path.exists(local_path):
                if filename.lower().endswith('.xml'):
                    from modules.parser_xml import parse_xml_license
                    license_data = parse_xml_license(local_path)
                else:
                    from modules.parser_dat import parse_dat_license
                    license_data = parse_dat_license(local_path)
                
                if license_data:
                    # Извлекаем значения
                    values = extract_dynamic_values_from_license(license_data, extraction_rules)
                    
                    # Если указана конкретная колонка
                    if column_id and column_config:
                        rule_id = column_config.get('rule_id')
                        capacity_key = column_config.get('capacity_key')
                        if rule_id and rule_id in values:
                            set_dynamic_value(lic_id, column_id, values[rule_id])
                        elif capacity_key:
                            # Для фич
                            for res in license_data.get('resources', []):
                                if res['name'] == capacity_key:
                                    set_dynamic_value(lic_id, column_id, res['value'])
                                    break
                    
                    updated += 1
        except Exception as e:
            errors += 1
            print(f"Ошибка обновления лицензии {lic_id}: {e}")
    
    return updated, errors


def get_available_capacity_keys(operator):
    """
    Получает список всех уникальных CapacityKey, встречающихся в лицензиях оператора
    """
    from modules.database import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT r.capacity_key
        FROM resources r
        JOIN licenses l ON r.license_id = l.id
        WHERE l.operator = ?
        ORDER BY r.capacity_key
    ''', (operator,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [r[0] for r in rows if r[0]]