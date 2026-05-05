# modules/capacity_mapper.py
"""
Модуль для загрузки описаний CapacityKey из Excel файлов
Файлы: license_details/{domain}_license_details.xlsx
"""

import os
import openpyxl
from modules.logger import get_logger

logger = get_logger(__name__)

# Кэш описаний (загружается один раз)
_capacity_descriptions_cache = {}


def load_capacity_descriptions(domain, network_storage_path):
    """
    Загружает описания CapacityKey из Excel файла для указанного домена
    
    Args:
        domain: str - имя домена (например, 'CScore')
        network_storage_path: str - путь к корню сетевого хранилища
    
    Returns:
        dict: {capacity_key: {'description': str, 'unit': str}}
    """
    global _capacity_descriptions_cache
    
    # Проверяем кэш
    if domain in _capacity_descriptions_cache:
        return _capacity_descriptions_cache[domain]
    
    file_path = os.path.join(network_storage_path, 'license_details', f'{domain}_license_details.xlsx')
    
    if not os.path.exists(file_path):
        logger.warning(f"Файл описаний не найден: {file_path}")
        return {}
    
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        
        # Определяем колонки из сохранённых настроек
        config = get_capacity_mapping_config()
        
        capacity_key_col = config.get('col_a', 'A')
        description_col = config.get('col_b', 'B')
        unit_col = config.get('col_c', 'C')
        
        # Преобразуем букву колонки в индекс (A->1, B->2)
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
        logger.info(f"Загружено {len(descriptions)} описаний для домена {domain}")
        
        return descriptions
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {file_path}: {e}")
        return {}


def get_capacity_description(capacity_key, domain, network_storage_path):
    """
    Получить описание для конкретного CapacityKey
    
    Args:
        capacity_key: str - код лицензии
        domain: str - домен
        network_storage_path: str - путь к сетевому хранилищу
    
    Returns:
        dict: {'description': str, 'unit': str} или None
    """
    descriptions = load_capacity_descriptions(domain, network_storage_path)
    return descriptions.get(capacity_key)


def get_capacity_mapping_config():
    """
    Получить настройки маппинга колонок из localStorage или файла
    """
    # Здесь можно читать из config.json или localStorage
    # Пока возвращаем значения по умолчанию
    return {
        'col_a': 'A',  # CapacityKey
        'col_b': 'B',  # Description
        'col_c': 'C'   # Unit
    }


def clear_cache():
    """Очистить кэш описаний"""
    global _capacity_descriptions_cache
    _capacity_descriptions_cache = {}