# modules/capacity_mapper.py
"""
Модуль для загрузки описаний CapacityKey из Excel файлов
Файлы: license_details/{domain}_license_details.xlsx
Поиск: сначала в сетевом хранилище, потом локально
"""

import os
import openpyxl
from modules.logger import get_logger
from flask import current_app

logger = get_logger(__name__)

# Кэш описаний (загружается один раз)
_capacity_descriptions_cache = {}

def _find_description_file(domain, network_storage_path, local_path):
    """
    Ищет файл описаний сначала в сетевом хранилище, потом локально
    """
    filename = f'{domain}_license_details.xlsx'
    
    # 1. Пробуем сетевой путь (только если файл существует)
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
    
    logger.warning(f"Файл описаний не найден для домена {domain} ни в одном из мест")
    return None

def load_capacity_descriptions(domain, network_storage_path):
    """
    Загружает описания CapacityKey из Excel файла для указанного домена
    """
    global _capacity_descriptions_cache
    
    if not domain:
        logger.warning("Домен не указан, пропускаем загрузку описаний")
        return {}
    
    # Проверяем кэш
    if domain in _capacity_descriptions_cache:
        return _capacity_descriptions_cache[domain]
    
    # Получаем локальный путь из конфига
    local_path = None
    try:
        from flask import current_app
        local_path = current_app.config.get('local_license_details_path', '')
    except:
        pass
    
    # Ищем файл
    file_path = _find_description_file(domain, network_storage_path, local_path)
    
    if not file_path:
        logger.warning(f"Файл описаний не найден для домена {domain}")
        return {}
    
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        
        config = get_capacity_mapping_config()
        capacity_key_col = config.get('col_a', 'A')
        description_col = config.get('col_b', 'B')
        unit_col = config.get('col_c', 'C')
        
        def col_letter_to_index(letter):
            return ord(letter.upper()) - 64
        
        col_idx_key = col_letter_to_index(capacity_key_col)
        col_idx_desc = col_letter_to_index(description_col)
        col_idx_unit = col_letter_to_index(unit_col)
        
        descriptions = {}
        
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[col_idx_key - 1]:
                continue
            
            capacity_key = str(row[col_idx_key - 1]).strip()
            description = str(row[col_idx_desc - 1]).strip() if col_idx_desc <= len(row) else ''
            unit = str(row[col_idx_unit - 1]).strip() if col_idx_unit <= len(row) else ''
            
            if capacity_key:
                descriptions[capacity_key] = {
                    'description': description,
                    'unit': unit
                }
        
        _capacity_descriptions_cache[domain] = descriptions
        logger.info(f"Загружено {len(descriptions)} описаний для домена {domain} из {file_path}")
        
        return descriptions
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {file_path}: {e}")
        return {}

def get_capacity_description(capacity_key, domain, network_storage_path):
    """
    Получить описание для конкретного CapacityKey
    """
    if not domain or not capacity_key:
        return None
    
    descriptions = load_capacity_descriptions(domain, network_storage_path)
    return descriptions.get(capacity_key)

def get_capacity_mapping_config():
    """
    Получить настройки маппинга колонок
    """
    return {
        'col_a': 'A',  # CapacityKey
        'col_b': 'B',  # Description
        'col_c': 'C'   # Unit
    }

def clear_cache():
    """Очистить кэш описаний"""
    global _capacity_descriptions_cache
    _capacity_descriptions_cache = {}