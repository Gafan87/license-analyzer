# modules/capacity_mapper.py
"""
Модуль для загрузки описаний CapacityKey из Excel файлов
Файлы: license_details/{domain}_license_details.xlsx
Поиск: сначала в сетевом хранилище, потом локально
Поддерживает маппинг NE Type -> Domain -> Файл описаний
"""

import os
import openpyxl
from modules.logger import get_logger
from flask import current_app
import math

logger = get_logger(__name__)

# Кэш описаний (загружается один раз)
_capacity_descriptions_cache = {}

# Кэш для маппинга NE Type -> Domain -> Файл
_ne_type_mapping_cache = None

def roundup(value, decimals=0):
    """Округление вверх до указанного количества знаков"""
    multiplier = 10 ** decimals
    return math.ceil(value * multiplier) / multiplier

def load_ne_type_mapping(mapping_file=None):
    """
    Загружает маппинг NE Type -> Domain -> Файл описаний из Excel
    """
    global _ne_type_mapping_cache
    
    if _ne_type_mapping_cache is not None:
        return _ne_type_mapping_cache
    
    # Если путь не передан, пытаемся получить из конфига
    if mapping_file is None:
        try:
            from flask import current_app
            mapping_file = current_app.config.get('ne_type_mapping_file')
        except (ImportError, RuntimeError):
            # Вне контекста Flask, пробуем прочитать config.json напрямую
            import json
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    mapping_file = config.get('ne_type_mapping_file')
            except:
                mapping_file = None
    
    # Если путь всё ещё не определён, используем стандартный
    if not mapping_file:
        mapping_file = 'mapping/ne_type_mapping.xlsx'
    
    # Пробуем разные варианты пути
    if not os.path.exists(mapping_file):
        # Пробуем с сетевым путём
        alt_path1 = r'\\A00742028-C5NC5\_Licenses\mapping\ne_type_mapping.xlsx'
        if os.path.exists(alt_path1):
            mapping_file = alt_path1
    
    if not os.path.exists(mapping_file):
        # Пробуем с прямыми слешами
        alt_path2 = '//A00742028-C5NC5/_Licenses/mapping/ne_type_mapping.xlsx'
        if os.path.exists(alt_path2):
            mapping_file = alt_path2
    
    if not os.path.exists(mapping_file):
        logger.warning(f"Файл маппинга NE Type не найден: {mapping_file}")
        return {}
    
    try:
        wb = openpyxl.load_workbook(mapping_file, data_only=True)
        sheet = wb.active
        
        mapping = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            
            ne_type = str(row[0]).strip() if row[0] else ''
            domain = str(row[1]).strip() if row[1] else ''
            details_file = str(row[2]).strip() if row[2] else ''
            sheet_name = str(row[3]).strip() if row[3] else ''
            
            if ne_type:
                mapping[ne_type] = {
                    'domain': domain,
                    'details_file': details_file,
                    'sheet_name': sheet_name
                }
        
        _ne_type_mapping_cache = mapping
        logger.info(f"Загружен маппинг NE Type: {len(mapping)} записей из {mapping_file}")
        return mapping
        
    except Exception as e:
        logger.error(f"Ошибка загрузки маппинга NE Type: {e}")
        return {}


def reload_mapping():
    """Принудительная перезагрузка маппинга NE Type"""
    global _ne_type_mapping_cache
    _ne_type_mapping_cache = None
    return load_ne_type_mapping()

def get_description_file_and_sheet(ne_type):
    """
    Получает имя файла описаний и имя листа для NE типа
    Returns:
        dict: {'domain': str, 'details_file': str, 'sheet_name': str} или None
    """
    mapping = load_ne_type_mapping()
    return mapping.get(ne_type, {})


def _col_letter_to_index(letter):
    """Преобразует букву колонки в индекс (A->1, B->2)"""
    return ord(letter.upper()) - 64


def _find_description_file(filename, network_storage_path, local_path):
    """
    Ищет файл описаний сначала в сетевом хранилище, потом локально
    """
    # 1. Пробуем сетевой путь
    if network_storage_path:
        remote_file = os.path.join(network_storage_path, 'license_details', filename)
        if os.path.exists(remote_file):
            logger.info(f"Файл найден в сетевом хранилище: {remote_file}")
            return remote_file
        else:
            logger.debug(f"Файл не найден в сетевом хранилище: {remote_file}")
    
    # 2. Пробуем локальный путь из конфига
    if local_path:
        local_file = os.path.join(local_path, filename)
        if os.path.exists(local_file):
            logger.info(f"Файл найден локально: {local_file}")
            return local_file
        else:
            logger.debug(f"Файл не найден локально: {local_file}")
    
    # 3. Пробуем относительный путь (в папке проекта)
    project_file = os.path.join('license_details', filename)
    if os.path.exists(project_file):
        logger.info(f"Файл найден в папке проекта: {project_file}")
        return project_file
    
    logger.warning(f"Файл описаний не найден: {filename}")
    return None


def get_capacity_mapping_config(operator_name=None):
    """Возвращает конфиг колонок. formula_col и Sh_col определяются динамически по operator_name"""
    config = {
        'col_key': 'A',
        'col_desc': 'B',
        'col_unit': 'C',
        'col_part': 'D',
        'col_type': 'E',
        'col_parent': 'F',
        'col_spart_coeff': 'G',
        'col_is_main': 'H',
    }
    # formula и sharing определяются динамически из заголовков
    return config

def load_sharing_from_excel(file_path):
    """
    Загружает вкладку 'Sharing' из targets.xlsx.

    Структура листа:
        Operator | Domain | NE types | Share_Group | CopyFrom | <Cities...>

    Возвращает:
        {
            ('beeline', 'UGW'): {
                'domain': 'PS',
                'share_group': 'GGSN',
                'copy_from': None,
                'sh': {'MSK': 4, 'SPb': 2}
            },
            ('beeline', 'UDG'): {
                'domain': 'vEPC',
                'share_group': None,
                'copy_from': 'UNC(CGW)',
                'sh': {'MSK': 4, 'SPb': 2}
            },
            ...
        }

    Правила (см. спецификацию):
        - Одна строка = один NE type
        - (Operator, NE types) уникален — побеждает последняя
        - Share_Group и CopyFrom взаимоисключающие
        - Цепочки CopyFrom — warning
        - Пустая ячейка города = нет значения
    """
    FIXED_COLUMNS = {'Operator', 'Domain', 'NE types', 'Share_Group', 'CopyFrom'}

    if not os.path.exists(file_path):
        logger.warning(f"Файл Sharing не найден: {file_path}")
        return {}

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)

        if 'Sharing' not in wb.sheetnames:
            logger.warning(f"Лист 'Sharing' не найден в {file_path}")
            return {}

        sheet = wb['Sharing']

        # ========== ЧИТАЕМ ЗАГОЛОВКИ ==========
        headers = []
        for cell in next(sheet.iter_rows(min_row=1, max_row=1)):
            headers.append(str(cell.value).strip() if cell.value else '')

        # Карта колонок
        col_map = {}       # {name: idx} для фиксированных
        city_cols = {}     # {city: idx}

        for i, h in enumerate(headers):
            if not h:
                continue
            if h in FIXED_COLUMNS:
                col_map[h] = i
            else:
                city_cols[h] = i

        # Проверка обязательных колонок
        required = ['Operator', 'NE types']
        missing = [c for c in required if c not in col_map]
        if missing:
            logger.error(f"Отсутствуют обязательные колонки в Sharing: {missing}")
            return {}

        if not city_cols:
            logger.warning("Не найдено ни одной колонки-города в Sharing")
            return {}

        col_operator = col_map['Operator']
        col_domain = col_map.get('Domain')
        col_ne = col_map['NE types']
        col_share_group = col_map.get('Share_Group')
        col_copy_from = col_map.get('CopyFrom')

        logger.info(f"Sharing: города = {list(city_cols.keys())}")

        # ========== ЧИТАЕМ СТРОКИ ==========
        sharing = {}
        duplicates = []

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) <= col_ne:
                continue

            # Operator и NE types — обязательные
            operator = str(row[col_operator]).strip() if col_operator < len(row) and row[col_operator] else ''
            ne_type = str(row[col_ne]).strip() if col_ne < len(row) and row[col_ne] else ''

            if not operator or not ne_type:
                continue

            # Опциональные
            domain = str(row[col_domain]).strip() if col_domain is not None and col_domain < len(row) and row[col_domain] else ''
            share_group = str(row[col_share_group]).strip() if col_share_group is not None and col_share_group < len(row) and row[col_share_group] else None
            copy_from = str(row[col_copy_from]).strip() if col_copy_from is not None and col_copy_from < len(row) and row[col_copy_from] else None

            # Города
            sh = {}
            for city, col_idx in city_cols.items():
                if col_idx >= len(row):
                    continue
                val = row[col_idx]
                if val is None or val == '':
                    continue
                try:
                    sh[city] = int(val)
                except (ValueError, TypeError):
                    try:
                        sh[city] = int(float(val))
                    except (ValueError, TypeError):
                        logger.warning(f"Sharing[{row_idx}]: {city} = '{val}' не число")
                        continue

            key = (operator, ne_type)
            if key in sharing:
                duplicates.append(key)

            sharing[key] = {
                'domain': domain,
                'share_group': share_group,
                'copy_from': copy_from,
                'sh': sh,
            }

        # ========== ПРОВЕРКА ==========
        # 1. Конфликт Share_Group + CopyFrom
        conflicts = [ne for (op, ne), info in sharing.items()
                     if info['share_group'] and info['copy_from']]
        if conflicts:
            logger.warning(f"Sharing: Share_Group и CopyFrom одновременно: {conflicts}")

        # 2. Цепочки CopyFrom
        chains = []
        for (op, ne), info in sharing.items():
            src = info.get('copy_from')
            if not src:
                continue
            if (op, src) in sharing and sharing[(op, src)].get('copy_from'):
                chains.append(f"{ne}→{src}→{sharing[(op, src)]['copy_from']}")
        if chains:
            logger.warning(f"Sharing: цепочки CopyFrom: {chains}")

        if duplicates:
            logger.warning(f"Sharing: дубликаты (Operator, NE types): {duplicates}")

        logger.info(f"Sharing загружен: {len(sharing)} NE types из {file_path}")
        return sharing

    except Exception as e:
        logger.error(f"Ошибка загрузки Sharing: {e}", exc_info=True)
        return {}

def load_capacity_descriptions(domain, network_storage_path, ne_type=None, operator_name=None):
    """
    Загружает описания CapacityKey из Excel файла для указанного домена
    
    Args:
        domain: str - имя домена (например, 'CScore')
        network_storage_path: str - путь к корню сетевого хранилища
        ne_type: str - тип NE (опционально, для маппинга)
        operator_name: str - имя оператора для поиска колонок Formula_{op}
    
    Returns:
        dict: {capacity_key: {description, unit, part_number, type, parent, formula, sharing, ...}}
    """
    global _capacity_descriptions_cache
    
    if not domain:
        logger.warning("Домен не указан, пропускаем загрузку описаний")
        return {}
    
    # Определяем файл и лист по NE типу, если передан
    details_file = None
    sheet_name = None
    
    if ne_type:
        mapping = get_description_file_and_sheet(ne_type)
        if mapping:
            details_file = mapping.get('details_file')
            sheet_name = mapping.get('sheet_name')
            if mapping.get('domain'):
                domain = mapping['domain']
    
    if not details_file:
        details_file = f'{domain}_license_details.xlsx'
    
    cache_key = f"{domain}_{details_file}_{sheet_name or 'active'}_{operator_name or 'default'}"
    
    if cache_key in _capacity_descriptions_cache:
        return _capacity_descriptions_cache[cache_key]
    
    local_path = None
    try:
        local_path = current_app.config.get('local_license_details_path', '')
    except:
        pass
    
    file_path = _find_description_file(details_file, network_storage_path, local_path)
    
    if not file_path:
        logger.warning(f"Файл описаний не найден для домена {domain}: {details_file}")
        return {}
    
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        
        if sheet_name and sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            logger.info(f"Используем лист '{sheet_name}' из {file_path}")
        else:
            sheet = wb.active
            if sheet_name:
                logger.debug(f"Лист '{sheet_name}' не найден, используем активный")
        
        # Читаем заголовки для поиска колонок Formula_{op} и Sh_{op}
        headers = [str(cell.value).strip().lower() if cell.value else '' for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        
        config = get_capacity_mapping_config()
        
        col_idx_key = _col_letter_to_index(config['col_key'])
        col_idx_desc = _col_letter_to_index(config['col_desc'])
        col_idx_unit = _col_letter_to_index(config['col_unit'])
        col_idx_part = _col_letter_to_index(config['col_part'])
        col_idx_type = _col_letter_to_index(config['col_type'])
        col_idx_parent = _col_letter_to_index(config['col_parent'])
        col_idx_spart_coeff = _col_letter_to_index(config['col_spart_coeff'])
        col_idx_is_main = _col_letter_to_index(config['col_is_main'])
        
        # Ищем колонки Formula_{op} и Sh_{op} по имени оператора
        formula_col = None
        Sh_col = None
        if operator_name:
            for i, h in enumerate(headers):
                if h == f'formula_{operator_name}':
                    formula_col = i
                elif h == f'Sh_{operator_name}':
                    Sh_col = i
        
        descriptions = {}
        
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[col_idx_key - 1]:
                continue
            
            capacity_key = str(row[col_idx_key - 1]).strip()
            description = str(row[col_idx_desc - 1]).strip() if col_idx_desc <= len(row) and row[col_idx_desc - 1] else ''
            unit = str(row[col_idx_unit - 1]).strip() if col_idx_unit <= len(row) and row[col_idx_unit - 1] else ''                            
            part_number = str(row[col_idx_part - 1]).strip() if col_idx_part <= len(row) and row[col_idx_part - 1] else ''
            key_type = str(row[col_idx_type - 1]).strip().lower() if col_idx_type <= len(row) and row[col_idx_type - 1] else 'bpart'
            
                        # Dimensioning — только для variable (число = шаг округления)
            dimensioning = 0
            if key_type == 'variable' and unit:
                try:
                    dimensioning = float(unit)
                except (ValueError, TypeError):
                    dimensioning = 0
            
            parent = str(row[col_idx_parent - 1]).strip() if col_idx_parent <= len(row) and row[col_idx_parent - 1] else ''
            spart_coeff = str(row[col_idx_spart_coeff - 1]).strip() if col_idx_spart_coeff <= len(row) and row[col_idx_spart_coeff - 1] else ''
            is_main_for_spart = str(row[col_idx_is_main - 1]).strip().upper() == 'TRUE' if col_idx_is_main <= len(row) and row[col_idx_is_main - 1] else False
            
            # Читаем formula и sharing для оператора
            formula = ''
            sharing = 1
            if formula_col is not None and formula_col < len(row) and row[formula_col]:
                formula = str(row[formula_col]).strip()
            if Sh_col is not None and Sh_col < len(row) and row[Sh_col]:
                try:
                    sharing = int(row[Sh_col])
                except (ValueError, TypeError):
                    sharing = 1
            
            if capacity_key:
                descriptions[capacity_key] = {
                    'description': description,
                    'unit': unit,
                    'dimensioning': dimensioning,
                    'part_number': part_number,
                    'type': key_type,
                    'parent': parent if parent else None,
                    'is_main': key_type == 'main',
                    'valid_date': '',
                    'spart_coeff': spart_coeff if spart_coeff else None,
                    'is_main_for_spart': is_main_for_spart,
                    'formula': formula if formula else None,
                    'sharing': sharing
                }
        
        _capacity_descriptions_cache[cache_key] = descriptions
        logger.info(f"Загружено {len(descriptions)} описаний для домена {domain}, оператор: {operator_name or 'default'}")
        
        return descriptions
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {file_path}: {e}")
        return {}
       
def load_full_capacity_list(domain, network_storage_path, ne_type=None, operator_name=None):
    descriptions = load_capacity_descriptions(domain, network_storage_path, ne_type, operator_name)
    
    result = []
    sort_order = 0
    for cap_key, info in descriptions.items():
        item_type = info.get('type', 'bpart')
        
        result.append({
            'name': cap_key,
            'type': item_type,
            'parent': info.get('parent'),
            'part_number': info.get('part_number', ''),
            'dimension': info.get('unit', ''),
            'dimensioning': info.get('dimensioning', 0),
            'description': info.get('description', ''),
            'is_main': info.get('is_main', False),
            'is_main_for_spart': info.get('is_main_for_spart', False),
            'is_section': item_type == 'section',
            'spart_coeff': info.get('spart_coeff'),
            'formula': info.get('formula'),
            'sharing': info.get('sharing', 1),
            'sort_order': sort_order
        })
        sort_order += 1
    
    return result

def load_license_structure(domain, network_storage_path, ne_type=None):
    """
    Загружает полную структуру лицензии из Excel файла описаний
    Возвращает список SPart с их BPart (как в файле)
    """
    descriptions = load_capacity_descriptions(domain, network_storage_path, ne_type)
    
    # Группируем по SPart
    sparts_dict = {}
    
    for cap_key, info in descriptions.items():
        key_type = info.get('type', 'bpart')
        parent = info.get('parent')
        
        if key_type == 'spart':
            sparts_dict[cap_key] = {
                'name': cap_key,
                'value': 0,
                'valid_date': '',
                'part_number': info.get('part_number', ''),
                'dimension': info.get('unit', ''),
                'description': info.get('description', ''),
                'children': []
            }
        elif key_type == 'bpart' and parent:
            if parent in sparts_dict:
                sparts_dict[parent]['children'].append({
                    'name': cap_key,
                    'value': 0,
                    'valid_date': '',
                    'part_number': info.get('part_number', ''),
                    'dimension': info.get('unit', ''),
                    'description': info.get('description', ''),
                    'is_main': info.get('is_main', False)
                })
    
    # Сортируем SPart по порядку появления в файле
    return list(sparts_dict.values())

def get_capacity_description(capacity_key, domain, network_storage_path, ne_type=None):
    """Получить описание для конкретного CapacityKey (без привязки к оператору)"""
    if not domain or not capacity_key:
        return None
    descriptions = load_capacity_descriptions(domain, network_storage_path, ne_type)
    return descriptions.get(capacity_key)


def get_all_capacity_descriptions(domain, network_storage_path, ne_type=None):
    """
    Получить все описания для домена
    """
    return load_capacity_descriptions(domain, network_storage_path, ne_type)


def clear_cache():
    """Очистить кэш описаний"""
    global _capacity_descriptions_cache, _ne_type_mapping_cache
    _capacity_descriptions_cache = {}
    _ne_type_mapping_cache = None


def reload_mapping():
    """Принудительная перезагрузка маппинга NE Type"""
    global _ne_type_mapping_cache
    _ne_type_mapping_cache = None
    return load_ne_type_mapping()

def load_targets_from_excel(file_path, operator_name=None):
    """
    Загружает вкладку 'Targets' из targets.xlsx.

    Структура:
        Operator | Domain | Group | Unit | TargetKey | <Cities...>

    Возвращает:
        {
            ('beeline', 'PS,vEPC_GGSN_kBearers'): {
                'domain': 'PS,vEPC',
                'group': 'GGSN',
                'unit': 'kBearers',
                'city_values': {'MSK': 12768.0, 'SPb': 9000.0}
            },
            ...
        }
    """
    FIXED_COLUMNS = {'Operator', 'Domain', 'Group', 'Unit', 'TargetKey'}

    if not os.path.exists(file_path):
        logger.warning(f"Файл Targets не найден: {file_path}")
        return {}

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)

        if 'Targets' not in wb.sheetnames:
            logger.warning(f"Лист 'Targets' не найден в {file_path}")
            return {}

        sheet = wb['Targets']
        headers = [str(cell.value).strip() if cell.value else ''
                   for cell in next(sheet.iter_rows(min_row=1, max_row=1))]

        col_map = {}
        city_cols = {}

        for i, h in enumerate(headers):
            if not h:
                continue
            if h in FIXED_COLUMNS:
                col_map[h] = i
            else:
                city_cols[h] = i

        required = ['Operator', 'TargetKey']
        missing = [c for c in required if c not in col_map]
        if missing:
            logger.error(f"Отсутствуют обязательные колонки в Targets: {missing}")
            return {}

        if not city_cols:
            logger.warning("Не найдено ни одной колонки-города в Targets")
            return {}

        col_operator = col_map['Operator']
        col_domain = col_map.get('Domain')
        col_group = col_map.get('Group')
        col_unit = col_map.get('Unit')
        col_target_key = col_map['TargetKey']

        logger.info(f"Targets: города = {list(city_cols.keys())}")

        targets = {}
        duplicates = []

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) <= col_target_key:
                continue

            operator = str(row[col_operator]).strip() if col_operator < len(row) and row[col_operator] else ''
            target_key = str(row[col_target_key]).strip() if col_target_key < len(row) and row[col_target_key] else ''

            if not operator or not target_key:
                continue

            domain = str(row[col_domain]).strip() if col_domain is not None and col_domain < len(row) and row[col_domain] else ''
            group = str(row[col_group]).strip() if col_group is not None and col_group < len(row) and row[col_group] else ''
            unit = str(row[col_unit]).strip() if col_unit is not None and col_unit < len(row) and row[col_unit] else ''

            city_values = {}
            for city, col_idx in city_cols.items():
                if col_idx >= len(row):
                    continue
                val = row[col_idx]
                if val is None or val == '':
                    continue
                try:
                    city_values[city] = float(val)
                except (ValueError, TypeError):
                    logger.warning(f"Targets[{row_idx}]: {city} = '{val}' не число")
                    continue

            key = (operator, target_key)
            if key in targets:
                duplicates.append(key)

            targets[key] = {
                'domain': domain,
                'group': group,
                'unit': unit,
                'city_values': city_values,
            }

        if duplicates:
            logger.warning(f"Targets: дубликаты TargetKey: {duplicates}")

        logger.info(f"Targets загружены: {len(targets)} ключей из {file_path}")
        return targets

    except Exception as e:
        logger.error(f"Ошибка загрузки Targets: {e}", exc_info=True)
        return {}
    
def load_sharing_cities(file_path):
    """Возвращает список всех городов из заголовков Sharing (порядок как в Excel)."""
    if not os.path.exists(file_path):
        return []
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        if 'Sharing' not in wb.sheetnames:
            return []
        sh = wb['Sharing']
        headers = [cell.value for cell in next(sh.iter_rows(min_row=1, max_row=1))]
        FIXED = {'Operator', 'Domain', 'NE types', 'Share_Group', 'CopyFrom'}
        cities = [str(h).strip() for h in headers if h and str(h).strip() not in FIXED]
        wb.close()
        return cities
    except Exception as e:
        logger.error(f"Ошибка загрузки городов Sharing: {e}")
        return []
       
def compute_license_targets(targets, sharing_map, capacity_list, operator_name=None, extra_values=None):
    """
    ...
    extra_values: {type_name: {(var_name, city): value}} — значения из других NE
                  (например, {'SGSN': {...}, 'GGSN': {...}})
    """
    if extra_values is None:
        extra_values = {}
    """
    Вычисляет целевые значения для каждой комбинации (TargetKey, city, NE, CapacityKey).

    Логика:
        1. TargetKey = ёмкость на город (из Targets.xlsx)
        2. Sharing делит между NE-типами (share_nodes / copy_nodes)
        3. Значение на 1 экземпляр
        4. Формулы из license_details:
           - Фиксированное число
           - Прямая ссылка на TargetKey
           - Умножение: TargetKey * N
           - Сумма: A + B + C
           - Проценты: TargetKey * X%
           - Функции: roundup(x, N), round(x, N), max(...), min(...), if(cond, a, b)
        5. target_value = НА 1 ЭКЗЕМПЛЯР
    """
    import re
    import math

    logger_local = get_logger(__name__)
    results = []

    # ========== 1. Города текущего NE ==========
    ne_type_current = capacity_list[0].get('ne_type', '') if capacity_list else ''
    ne_cities = set()
    key = (operator_name, ne_type_current)
    if key in sharing_map:
        # Только города, где NE реально участвует (sh > 0)
        ne_cities = {
            city for city, sh_val in sharing_map[key]['sh'].items()
            if sh_val > 0
        }

    logger_local.info(f"compute_license_targets для NE {ne_type_current}: города = {sorted(ne_cities)}")

    # ========== 2. Построение targets_map ==========
    # {tk: {domain, group, city_values: {city: value}}}
    targets_map = {}
    for (op, tk), info in targets.items():
        if op != operator_name:
            continue
        targets_map[tk] = {
            'domain': info.get('domain', ''),
            'group': info.get('group', ''),
            'city_values': info.get('city_values', {}),
        }

    if not targets_map:
        logger_local.warning(f"Нет TargetKey для оператора {operator_name}")
        return []

    # ========== 3. Утилиты ==========
    def domain_intersects(d1, d2):
        if not d1 or not d2:
            return False
        set1 = {x.strip().lower() for x in d1.split(',') if x.strip()}
        set2 = {x.strip().lower() for x in d2.split(',') if x.strip()}
        return bool(set1 & set2)

    all_nes = {ne: info for (op, ne), info in sharing_map.items() if op == operator_name}

    # ========== 4. Шаринг ==========
    def compute_sharing_values(tk, city):
        """
        Для TargetKey + city возвращает {ne_type: value_per_instance}.
        Значение — НА 1 ЭКЗЕМПЛЯР.
        """
        info = targets_map.get(tk)
        if not info:
            return {}
        group = info['group']
        domain = info['domain']
        value = info['city_values'].get(city)
        if value is None:
            return {}

        # --- Share-nodes ---
        share_nodes = {}
        for ne, ne_info in all_nes.items():
            if ne_info.get('share_group') != group:
                continue
            if not domain_intersects(ne_info.get('domain', ''), domain):
                continue
            ne_sh = ne_info['sh'].get(city, 0)
            if ne_sh and ne_sh > 0:
                share_nodes[ne] = ne_info

        if not share_nodes:
            return {}

        sum_sh = sum(ne_info['sh'].get(city, 0) for ne_info in share_nodes.values())
        if sum_sh == 0:
            return {}

        # raw — на весь NE-тип
        raw = {}
        for ne, ne_info in share_nodes.items():
            ne_sh = ne_info['sh'].get(city, 0)
            raw[ne] = value * ne_sh / sum_sh

        # final — на 1 экземпляр
        final = {}
        for ne, ne_info in share_nodes.items():
            ne_sh = ne_info['sh'].get(city, 0)
            if not ne_sh:
                continue
            final[ne] = raw[ne] / ne_sh

        # --- Copy-nodes ---
        for ne, ne_info in all_nes.items():
            src = ne_info.get('copy_from')
            if not src or src not in raw:
                continue
            ne_sh = ne_info['sh'].get(city)
            if not ne_sh:
                continue
            final[ne] = raw[src] / ne_sh

        return final

    def get_target_value(tk, city, ne_type):
        """Значение TargetKey для NE (на 1 экземпляр) или None."""
        return compute_sharing_values(tk, city).get(ne_type)

    # ========== 5. Вычисление формул ==========
    def _val(token, city, spart_targets, ne_type):
        """
        Значение токена: TargetKey (с шарингом) / SPart (уже посчитан) / число.
        Поиск регистронезависимый.
        """
        token = token.strip()
        if not token:
            return None

        token_lower = token.lower()

        # 1. TargetKey — регистронезависимо
        tk_found = None
        if token in targets_map:
            tk_found = token
        else:
            for tk in targets_map.keys():
                if tk.lower() == token_lower:
                    tk_found = tk
                    break
        if tk_found:
            return get_target_value(tk_found, city, ne_type)

        # 2. SPart / Variable — регистронезависимо
        sp_found = None
        if token in spart_targets:
            sp_found = token
        else:
            for sp_name in spart_targets.keys():
                if sp_name.lower() == token_lower:
                    sp_found = sp_name
                    break
        if sp_found and city in spart_targets[sp_found]:
            return spart_targets[sp_found][city]

        # 3. Число
        try:
            return float(token)
        except (ValueError, TypeError):
            return None
        
    def eval_simple(expr, city, spart_targets, ne_type):
        """Простое арифметическое выражение: + - * /."""
        try:
            tokens = re.split(r'([+\-*/])', expr)
            result = None
            current_op = '+'
            for token in tokens:
                token = token.strip()
                if not token:
                    continue
                if token in ('+', '-', '*', '/'):
                    current_op = token
                    continue
                v = _val(token, city, spart_targets, ne_type)
                if v is None:
                    return None
                if result is None:
                    result = v
                elif current_op == '+':
                    result += v
                elif current_op == '-':
                    result -= v
                elif current_op == '*':
                    result *= v
                elif current_op == '/':
                    if v == 0:
                        return None
                    result /= v
            return result
        except Exception:
            return None

    def split_args(s):
        if ';' in s:
            return [x.strip() for x in s.split(';')]
        if ',' in s:
            return [x.strip() for x in s.split(',')]
        return [s.strip()]

    def eval_condition(cond, city, spart_targets, ne_type):
        cond_orig = cond.strip()          # ← оригинал для аргументов
        cond_lower = cond_orig.lower()    # ← нижний для операторов

        if ' and ' in cond_lower:
            parts = [p.strip() for p in cond_orig.split(' and ')]  # ← оригинал
            return all(eval_condition(p, city, spart_targets, ne_type) for p in parts)
        if ' or ' in cond_lower:
            parts = [p.strip() for p in cond_orig.split(' or ')]   # ← оригинал
            return any(eval_condition(p, city, spart_targets, ne_type) for p in parts)
        for op in ('>=', '<=', '==', '!=', '>', '<'):
            if op in cond_orig:                                     # ← оригинал
                left, right = cond_orig.split(op, 1)                # ← оригинал
                lv = _val(left.strip(), city, spart_targets, ne_type) or 0
                rv = _val(right.strip(), city, spart_targets, ne_type) or 0
                if op == '>': return lv > rv
                if op == '<': return lv < rv
                if op == '>=': return lv >= rv
                if op == '<=': return lv <= rv
                if op == '==': return lv == rv
                if op == '!=': return lv != rv
        return False

    def eval_formula(formula_str, city, spart_targets, ne_type):
        """Вычисление формулы со всеми поддерживаемыми функциями."""
        f = formula_str.strip()
        f_lower = f.lower()

        # MAX
        m = re.match(r'max\((.+)\)$', f_lower, re.IGNORECASE)
        if m:
            # Используем f (оригинал) для аргументов
            inner = f[4:-1]  # отрезаем 'max(' и ')'
            vals = [_val(v, city, spart_targets, ne_type) for v in split_args(inner)]
            vals = [v for v in vals if v is not None]
            return max(vals) if vals else None

        # MIN
        m = re.match(r'min\((.+)\)$', f_lower, re.IGNORECASE)
        if m:
            inner = f[4:-1]
            vals = [_val(v, city, spart_targets, ne_type) for v in split_args(inner)]
            vals = [v for v in vals if v is not None]
            return min(vals) if vals else None

        # AVG
        m = re.match(r'avg\((.+)\)$', f_lower, re.IGNORECASE)
        if m:
            inner = f[4:-1]
            vals = [_val(v, city, spart_targets, ne_type) for v in split_args(inner)]
            vals = [v for v in vals if v is not None]
            return sum(vals) / len(vals) if vals else None

        # SUM
        m = re.match(r'sum\((.+)\)$', f_lower, re.IGNORECASE)
        if m:
            inner = f[4:-1]
            vals = [_val(v, city, spart_targets, ne_type) for v in split_args(inner)]
            vals = [v for v in vals if v is not None]
            return sum(vals) if vals else None

        # IF — ручной парсинг (устойчив к запятым внутри)
        if f_lower.startswith('if(') and f_lower.endswith(')'):
            inner = f[3:-1]  # убираем 'if(' и ')'
            # Парсим на верхнем уровне (без учёта вложенных скобок)
            depth = 0
            parts = []
            current = ''
            for ch in inner:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    parts.append(current.strip())
                    current = ''
                    continue
                current += ch
            if current:
                parts.append(current.strip())

            if len(parts) == 3:
                cond, vt, vf = parts
                if eval_condition(cond, city, spart_targets, ne_type):
                    return _val(vt, city, spart_targets, ne_type)
                return _val(vf, city, spart_targets, ne_type)

        # ROUNDUP
        m = re.match(r'roundup\((.+),\s*(-?\d+)\)$', f_lower, re.IGNORECASE)
        if m:
            # Извлекаем аргументы из ОРИГИНАЛА
            inner_str = f[8:]  # отрезаем 'roundup('
            # Ищем последнюю запятую перед числом
            last_comma = inner_str.rfind(',')
            expr = inner_str[:last_comma].strip()
            dec_str = inner_str[last_comma+1:].strip().rstrip(')')
            try:
                dec = int(dec_str)
            except ValueError:
                return None
            v = eval_simple(expr, city, spart_targets, ne_type)
            if v is None:
                return None
            mult = 10 ** dec
            return math.ceil(v * mult) / mult

        # ROUND
        m = re.match(r'round\((.+),\s*(-?\d+)\)$', f_lower, re.IGNORECASE)
        if m:
            inner_str = f[6:]  # отрезаем 'round('
            last_comma = inner_str.rfind(',')
            expr = inner_str[:last_comma].strip()
            dec_str = inner_str[last_comma+1:].strip().rstrip(')')
            try:
                dec = int(dec_str)
            except ValueError:
                return None
            v = eval_simple(expr, city, spart_targets, ne_type)
            if v is None:
                return None
            return roundup(v, dec)

        # CEIL
        m = re.match(r'ceil\((.+)\)$', f_lower, re.IGNORECASE)
        if m:
            inner = f[5:-1]
            v = eval_simple(inner, city, spart_targets, ne_type)
            return math.ceil(v) if v is not None else None

        # FLOOR
        m = re.match(r'floor\((.+)\)$', f_lower, re.IGNORECASE)
        if m:
            inner = f[6:-1]
            v = eval_simple(inner, city, spart_targets, ne_type)
            return math.floor(v) if v is not None else None

        # Простая арифметика
        return eval_simple(f, city, spart_targets, ne_type)

    # ========== 6. Обработка одного элемента ==========
    def process_item(item, spart_targets):
        """
        Возвращает (city_values, item_type) или (None, None).
        city_values: {city: value_per_instance}
        """
        formula = item.get('formula')
        if not formula:
            return None, None

        formula_str = str(formula).strip()
        name = item['name']
        ne_type = item.get('ne_type', ne_type_current)
        is_spart = item.get('type') == 'spart'
        
        
        # ========== 6.0.4 max_by_type(var, type1, type2, ...) [+ /N или *N] ==========
        if formula_str.lower().startswith('max_by_type('):
            try:
                # 1. Находим закрывающую скобку (с учётом вложенности)
                depth = 0
                close_pos = None
                for i, ch in enumerate(formula_str):
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                        if depth == 0:
                            close_pos = i
                            break
                if close_pos is None:
                    return None, None

                inner = formula_str[len('max_by_type('):close_pos]
                rest = formula_str[close_pos+1:].strip()  # например '/1000' или '*1000'

                parts = [p.strip() for p in inner.split(',')]
                if len(parts) < 2:
                    return None, None

                var_name = parts[0]
                type_names = parts[1:]

                # 2. Парсим множитель/делитель
                factor = 1.0
                factor_set = False
                if rest:
                    if rest.startswith('/'):
                        try:
                            factor = 1.0 / float(rest[1:].strip())
                            factor_set = True
                        except (ValueError, TypeError):
                            factor_set = False
                    elif rest.startswith('*'):
                        try:
                            factor = float(rest[1:].strip())
                            factor_set = True
                        except (ValueError, TypeError):
                            factor_set = False

                # 3. Вычисляем
                vals = {}
                for city in ne_cities:
                    max_val = None
                    for type_name in type_names:
                        type_values = extra_values.get(type_name, {})
                        v = type_values.get((var_name, city))
                        if v is not None:
                            if max_val is None or v > max_val:
                                max_val = v

                    if max_val is not None:
                        if factor_set:
                            result = max_val * factor
                        else:
                            result = max_val
                        vals[city] = roundup(result, 0)

                if vals:
                    return vals, 'variable'
                return None, None
            except Exception as e:
                logger_local.error(f"Ошибка max_by_type '{formula_str}': {e}")
                return None, None

        # ========== 6.0 fix:число ==========
        # Показываем только для городов, где есть Targets для этого NE
        if formula_str.lower().startswith('fix:'):
            try:
                fixed = float(formula_str[4:].strip())

                # Определяем города с Targets для этого NE
                cities_with_targets = set()
                ne_info = all_nes.get(ne_type, {})

                for tk, tk_info in targets_map.items():
                    tk_group = tk_info.get('group', '')
                    tk_domain = tk_info.get('domain', '')

                    # Проверяем, применим ли TargetKey к этому NE
                    applicable = False

                    # 1. NE в share_group этой группы
                    if ne_info.get('share_group') == tk_group:
                        if domain_intersects(ne_info.get('domain', ''), tk_domain):
                            applicable = True

                    # 2. NE копирует от NE в этой группе
                    elif ne_info.get('copy_from'):
                        src_info = all_nes.get(ne_info['copy_from'], {})
                        if src_info.get('share_group') == tk_group:
                            if domain_intersects(src_info.get('domain', ''), tk_domain):
                                applicable = True

                    if applicable:
                        cities_with_targets.update(tk_info['city_values'].keys())

                # Только пересечение ne_cities и cities_with_targets
                vals = {
                    city: roundup(fixed, 0)
                    for city in (ne_cities & cities_with_targets)
                }
                if vals:
                    return vals, 'variable'
                return None, None
            except (ValueError, TypeError):
                return None, None

        # ========== 6.1 Фиксированное число ==========
        try:
            fixed = float(formula_str)
            vals = {city: roundup(fixed, 0) for city in ne_cities}
            return vals, 'variable' if not is_spart else 'target'
        except (ValueError, TypeError):
            pass

        # ========== 6.2 Прямая ссылка на TargetKey ==========
        if formula_str in targets_map:
            vals = {}
            for city in targets_map[formula_str]['city_values'].keys():
                v = get_target_value(formula_str, city, ne_type)
                if v is not None:
                    vals[city] = roundup(v, 0)
            return vals, 'target'

        # ========== 6.3 Скобки: (A + B) * N, (A + B + C) * N, ... ==========
        # Формула типа "(A + B) * 1000"
        m = re.match(r'^\((.+)\)\s*\*\s*([\d.]+)$', formula_str)
        if m:
            inner = m.group(1)
            try:
                mult = float(m.group(2))
            except (ValueError, TypeError):
                mult = None
            if mult is not None:
                refs = [r.strip() for r in inner.split('+')]
                vals = {}
                for city in ne_cities:
                    total = 0
                    ok = True
                    for ref in refs:
                        v = _val(ref, city, spart_targets, ne_type)
                        if v is None:
                            ok = False
                            break
                        total += v
                    if ok:
                        vals[city] = roundup(total * mult, 0)
                if vals:
                    return vals, 'variable' if not is_spart else 'target'
                return None, None

        # ========== 6.4 Умножение: Ref * N ==========
        if '*' in formula_str and '%' not in formula_str and '(' not in formula_str:
            formula_clean = formula_str.replace(' ', '').replace(',', '')
            parts = formula_clean.split('*')
            if len(parts) == 2:
                ref = parts[0].strip()
                try:
                    mult = float(parts[1].strip())
                except (ValueError, TypeError):
                    mult = None

                if mult is not None:
                    # 1. TargetKey
                    tk_found = ref if ref in targets_map else None
                    if not tk_found:
                        for tk in targets_map.keys():
                            if tk.replace(',', '').replace(' ', '') == ref:
                                tk_found = tk
                                break
                    if tk_found:
                        vals = {}
                        for city in targets_map[tk_found]['city_values'].keys():
                            base = get_target_value(tk_found, city, ne_type)
                            if base is not None:
                                vals[city] = roundup(base * mult, 0)
                        return vals, 'target'

                    # 2. Variable/SPart
                    ref_found = None
                    if ref in spart_targets:
                        ref_found = ref
                    else:
                        for sp_name in spart_targets.keys():
                            if sp_name.lower() == ref.lower():
                                ref_found = sp_name
                                break
                    if ref_found:
                        vals = {}
                        for city in ne_cities:
                            base = spart_targets[ref_found].get(city)
                            if base is not None:
                                vals[city] = roundup(base * mult, 0)
                        if vals:
                            return vals, 'variable' if not is_spart else 'target'

        # ========== 6.5 Вычитание: A - B ==========
        if '-' in formula_str and '+' not in formula_str and '*' not in formula_str and '(' not in formula_str:
            parts = [p.strip() for p in formula_str.split('-')]
            if len(parts) == 2:
                left, right = parts
                vals = {}
                for city in ne_cities:
                    lv = _val(left, city, spart_targets, ne_type)
                    rv = _val(right, city, spart_targets, ne_type)
                    if lv is not None and rv is not None:
                        vals[city] = roundup(lv - rv, 0)
                if vals:
                    return vals, 'variable' if not is_spart else 'target'

        # ========== 6.6 Сумма: A + B + C ==========
        if '+' in formula_str and '(' not in formula_str:
            refs = [s.strip() for s in formula_str.split('+')]
            vals = {}
            for city in ne_cities:
                total = 0
                for ref in refs:
                    v = _val(ref, city, spart_targets, ne_type)
                    if v is None:
                        v = 0
                    total += v
                vals[city] = roundup(total, 0)
            return vals, 'variable' if not is_spart else 'target'

        # ========== 6.7 Проценты: Ref * X% ==========
        if '*' in formula_str and '%' in formula_str and '(' not in formula_str:
            parts = formula_str.split('*')
            ref = parts[0].strip()
            try:
                pct = float(parts[1].strip().replace('%', '')) / 100
                vals = {}
                for city in ne_cities:
                    base = _val(ref, city, spart_targets, ne_type)
                    if base is not None:
                        vals[city] = roundup(base * pct, 0)
                if vals:
                    return vals, 'variable' if not is_spart else 'target'
            except (ValueError, TypeError):
                pass

        # ========== 6.8 Функции (if, roundup, max, ...) ==========
        has_fn = any(f in formula_str.lower() for f in
                     ['max(', 'min(', 'avg(', 'sum(', 'if(', 'roundup(', 'round(', 'ceil(', 'floor('])
        if has_fn:
            vals = {}
            has_none = False
            for city in ne_cities:
                v = eval_formula(formula_str, city, spart_targets, ne_type)
                if v is not None:
                    vals[city] = roundup(v, 0)
                else:
                    # Данные ещё не готовы — откладываем на следующую итерацию
                    has_none = True
            
            if has_none:
                # Если хоть один город не посчитан — пробуем на следующей итерации
                return None, None
            
            return vals, 'variable' if not is_spart else 'target'

        # ========== 6.9 Простая ссылка на Variable/SPart ==========
        if formula_str in spart_targets:
            # SPart без формулы — не сохраняем (вычисляется на лету)
            if is_spart:
                return None, None
            # Variable — сохраняем
            vals = {city: spart_targets[formula_str][city]
                    for city in ne_cities
                    if city in spart_targets[formula_str]}
            return vals, 'variable'

        # ========== 6.10 Ничего не сработало ==========
        return None, None
    
    # ========== 7. Основной цикл ==========
    spart_targets = {}

    # 7.1 Сначала — spart и variable, независимо от порядка
    # Проходим в несколько итераций, пока есть прогресс
    remaining = [it for it in capacity_list if it['type'] in ('spart', 'variable')]
    max_iter = 10
    for _ in range(max_iter):
        progress = False
        still_remaining = []
        for item in remaining:
            name = item['name']
            if name in spart_targets:
                continue
            vals, item_type = process_item(item, spart_targets)
            if vals is not None:
                # Применяем dimensioning (только для variable)
                if item.get('type') == 'variable':
                    dim = item.get('dimensioning', 0)
                    if dim and dim > 0:
                        dim = float(dim)
                        vals = {city: roundup(v / dim) * dim for city, v in vals.items()}
                
                spart_targets[name] = vals
                for city, v in vals.items():
                    results.append({
                        'operator': operator_name or '',
                        'target_key': item.get('formula') or name,
                        'city': city,
                        'ne_type': item.get('ne_type', ne_type_current),
                        'capacity_key': name,
                        'target_value': v,
                        'item_type': item.get('type', 'target'),
                    })
                progress = True
            else:
                still_remaining.append(item)
        remaining = still_remaining
        if not progress:
            break

    # 7.2 Виртуальные SPart для TargetKey, которых нет в license_details
    for tk, info in targets_map.items():
        if tk in spart_targets:
            continue
        vals = {}
        for city in info['city_values'].keys():
            v = get_target_value(tk, city, ne_type_current)
            if v is not None:
                vals[city] = roundup(v, 0)
        if vals:
            spart_targets[tk] = vals
            for city, v in vals.items():
                results.append({
                    'operator': operator_name or '',
                    'target_key': tk,
                    'city': city,
                    'ne_type': ne_type_current,
                    'capacity_key': tk,
                    'target_value': v,
                    'item_type': 'target',
                })

    # 7.3 Финальная фильтрация: только города NE
    if ne_cities:
        results = [r for r in results if r['city'] in ne_cities]

    # 7.4 Сортировка
    results.sort(key=lambda r: (r['operator'], r['target_key'], r['city'], r['ne_type']))

    logger_local.info(f"Вычислено {len(results)} целевых значений")
    return results