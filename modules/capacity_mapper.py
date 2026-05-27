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

logger = get_logger(__name__)

# Кэш описаний (загружается один раз)
_capacity_descriptions_cache = {}

# Кэш для маппинга NE Type -> Domain -> Файл
_ne_type_mapping_cache = None

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


def get_capacity_mapping_config():
    return {
        'col_key': 'A',
        'col_desc': 'B',
        'col_unit': 'C',
        'col_part': 'D',
        'col_type': 'E',
        'col_parent': 'F',
        'col_spart_coeff': 'G',   # Для SPart: коэф. для MAIN BPart
        'col_is_main': 'H',       # Для BPart: TRUE/FALSE
        'col_formula': 'I'        # Универсальная формула
    }


def load_capacity_descriptions(domain, network_storage_path, ne_type=None):
    """
    Загружает описания CapacityKey из Excel файла для указанного домена
    
    Args:
        domain: str - имя домена (например, 'CScore')
        network_storage_path: str - путь к корню сетевого хранилища
        ne_type: str - тип NE (опционально, для маппинга)
    
    Returns:
        dict: {capacity_key: {'description': str, 'unit': str, 'part_number': str, 'type': str, 'parent': str}}
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
            # Если в маппинге указан другой домен, используем его
            if mapping.get('domain'):
                domain = mapping['domain']
    
    # Fallback: используем домен как имя файла
    if not details_file:
        details_file = f'{domain}_license_details.xlsx'
    
    cache_key = f"{domain}_{details_file}_{sheet_name or 'active'}"
    
    # Проверяем кэш
    if cache_key in _capacity_descriptions_cache:
        return _capacity_descriptions_cache[cache_key]
    
    # Получаем локальный путь из конфига
    local_path = None
    try:
        local_path = current_app.config.get('local_license_details_path', '')
    except:
        pass
    
    # Ищем файл
    file_path = _find_description_file(details_file, network_storage_path, local_path)
    
    if not file_path:
        logger.warning(f"Файл описаний не найден для домена {domain}: {details_file}")
        return {}
    
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        
        # Выбираем лист
        if sheet_name and sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            logger.info(f"Используем лист '{sheet_name}' из {file_path}")
        else:
            sheet = wb.active
            if sheet_name:
                logger.debug(f"Лист '{sheet_name}' не найден в {file_path}, используем активный")
        
        config = get_capacity_mapping_config()
        
        col_idx_key = _col_letter_to_index(config['col_key'])
        col_idx_desc = _col_letter_to_index(config['col_desc'])
        col_idx_unit = _col_letter_to_index(config['col_unit'])
        col_idx_part = _col_letter_to_index(config['col_part'])
        col_idx_type = _col_letter_to_index(config['col_type'])
        col_idx_parent = _col_letter_to_index(config['col_parent'])
        col_idx_spart_coeff = _col_letter_to_index(config['col_spart_coeff'])
        col_idx_is_main = _col_letter_to_index(config['col_is_main'])
        col_idx_formula = _col_letter_to_index(config.get('col_formula', 'I'))
        
        descriptions = {}
        
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[col_idx_key - 1]:
                continue
            
            capacity_key = str(row[col_idx_key - 1]).strip()
            description = str(row[col_idx_desc - 1]).strip() if col_idx_desc <= len(row) else ''
            unit = str(row[col_idx_unit - 1]).strip() if col_idx_unit <= len(row) else ''
            part_number = str(row[col_idx_part - 1]).strip() if col_idx_part <= len(row) else ''
            key_type = str(row[col_idx_type - 1]).strip().lower() if col_idx_type <= len(row) else 'bpart'
            parent = str(row[col_idx_parent - 1]).strip() if col_idx_parent <= len(row) else ''
            spart_coeff = str(row[col_idx_spart_coeff - 1]).strip() if col_idx_spart_coeff <= len(row) and row[col_idx_spart_coeff - 1] else ''
            is_main_for_spart = str(row[col_idx_is_main - 1]).strip().upper() == 'TRUE' if col_idx_is_main <= len(row) and row[col_idx_is_main - 1] else False
            formula = str(row[col_idx_formula - 1]).strip() if col_idx_formula <= len(row) and row[col_idx_formula - 1] else ''
            
            if capacity_key:
                descriptions[capacity_key] = {
                    'description': description,
                    'unit': unit,
                    'part_number': part_number,
                    'type': key_type,  # 'spart', 'bpart', 'main'
                    'parent': parent if parent else None,
                    'is_main': key_type == 'main',
                    'valid_date': '',
                    'spart_coeff': spart_coeff if spart_coeff else None,
                    'is_main_for_spart': is_main_for_spart,
                    'formula': formula if formula else None
                }
        
        _capacity_descriptions_cache[cache_key] = descriptions
        logger.info(f"Загружено {len(descriptions)} описаний для домена {domain} из файла {details_file}, лист: {sheet_name or 'active'}")
        
        return descriptions
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {file_path}: {e}")
        return {}
    
def load_full_capacity_list(domain, network_storage_path, ne_type=None):
    """
    Загружает полный список CapacityKey из Excel файла с сохранением порядка
    Поддерживает типы: spart, bpart, section (заголовок раздела)
    Возвращает список словарей с полями: name, type, parent, part_number, dimension, description, is_main
    """
    descriptions = load_capacity_descriptions(domain, network_storage_path, ne_type)
    
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
            'description': info.get('description', ''),
            'is_main': info.get('is_main', False),
            'is_main_for_spart': info.get('is_main_for_spart', False),
            'is_section': item_type == 'section',  # Флаг для заголовка раздела
            'sort_order': sort_order,
            'formula': info.get('formula'),
            'spart_coeff': info.get('spart_coeff'),
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
    """
    Получить описание для конкретного CapacityKey
    
    Args:
        capacity_key: str - код лицензии
        domain: str - домен
        network_storage_path: str - путь к сетевому хранилищу
        ne_type: str - тип NE (опционально)
    
    Returns:
        dict: {'description': str, 'unit': str, 'part_number': str, 'type': str, 'parent': str, 'is_main': bool}
    """
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


def load_targets_from_excel(file_path):
    """
    Загружает цели и формулы из Excel файла targets.xlsx
    Лист Targets: Operator, Domain, Type, City, Value, Unit
    Лист Formulas: Domain, Type, NE_Type, CapacityKey, Formula, Sharing, MainKey
    """
    if not os.path.exists(file_path):
        logger.warning(f"Файл целей не найден: {file_path}")
        return [], []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        
        # Загружаем базовые цели
        targets = []
        if 'Targets' in wb.sheetnames:
            sheet = wb['Targets']
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue
                targets.append({
                    'operator': str(row[0]).strip(),
                    'domain': str(row[1]).strip(),
                    'type': str(row[2]).strip(),
                    'city': str(row[3]).strip(),
                    'value': float(row[4]) if row[4] else 0,
                    'unit': str(row[5]).strip() if row[5] else ''
                })
        
        # Загружаем формулы
        formulas = []
        if 'Formulas' in wb.sheetnames:
            sheet = wb['Formulas']
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue
                formulas.append({
                    'domain': str(row[0]).strip(),
                    'type': str(row[1]).strip(),
                    'ne_type': str(row[2]).strip(),
                    'capacity_key': str(row[3]).strip(),
                    'formula': str(row[4]).strip(),
                    'sharing': int(row[5]) if row[5] else 1,
                    'main_key': str(row[6]).strip().upper() == 'YES'
                })
        
        logger.info(f"Загружено целей: {len(targets)}, формул: {len(formulas)}")
        return targets, formulas
        
    except Exception as e:
        logger.error(f"Ошибка загрузки целей: {e}")
        return [], []

def compute_license_targets(targets, formulas):
    """
    Вычисляет целевые значения для каждой комбинации город/NE_type/CapacityKey
    """
    results = []
    
    for target in targets:
        city = target['city']
        target_value = target['value']
        
        # Находим формулы для этого domain/type
        for formula in formulas:
            if formula['domain'] == target['domain'] and formula['type'] == target['type']:
                # Вычисляем значение по формуле
                try:
                    # Заменяем 'target' на значение и вычисляем
                    expr = formula['formula'].replace('target', str(target_value))
                    computed = eval(expr)
                    computed = computed / formula['sharing']
                    
                    results.append({
                        'operator': target['operator'],
                        'domain': target['domain'],
                        'type': target['type'],
                        'city': city,
                        'ne_type': formula['ne_type'],
                        'capacity_key': formula['capacity_key'],
                        'target_value': round(computed, 2)
                    })
                except Exception as e:
                    logger.error(f"Ошибка вычисления формулы {formula['formula']}: {e}")
    
    return results