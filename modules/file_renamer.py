import os
import re
import shutil
from datetime import datetime
from modules.parser_xml import parse_xml_license
from modules.parser_dat import parse_dat_license
from modules.esn_mapper import get_mapping_by_esn, get_mapping_by_lsn
from modules.logger import get_logger

logger = get_logger(__name__)

def extract_year_from_valid_date(valid_date):
    """Извлекает год из даты действия"""
    if valid_date == 'PERMANENT':
        return 'permanent'
    try:
        date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d')
        return str(date_obj.year)
    except:
        match = re.search(r'(\d{4})', valid_date)
        return match.group(1) if match else 'unknown'

def generate_new_filename(license_data, mapping):
    """Генерирует новое имя файла по правилам"""
    # Определяем компоненты
    product = license_data.get('product') or mapping.get('ne_type') or 'unknown'
    version = license_data.get('version') or 'unknown'
    city = mapping.get('city') or 'unknown'
    site = mapping.get('site') or 'unknown'
    
    # Год из validDate
    valid_date = license_data.get('valid_date', 'UNKNOWN')
    year = extract_year_from_valid_date(valid_date)
    
    # Формируем имя
    filename = f"{product}_{version}_{city}_{site}_{year}"
    
    # Добавляем расширение
    ext = '.xml' if license_data.get('file_type') == 'xml' else '.dat'
    
    return f"{filename}{ext}"

def rename_file_by_esn(file_path, target_folder, mapping_db=None):
    """
    Переименовывает файл по ESN и перемещает в целевую папку
    Возвращает: (success, new_path, message)
    """
    try:
        # Парсим файл
        if file_path.lower().endswith('.xml'):
            license_data = parse_xml_license(file_path)
        else:
            license_data = parse_dat_license(file_path)
        
        if not license_data:
            return False, None, "Не удалось распарсить файл"
        
        # Ищем ESN в маппинге
        esn = license_data.get('esn')
        lsn = license_data.get('lsn')
        
        mapping = None
        if esn:
            mapping = get_mapping_by_esn(esn)
        if not mapping and lsn:
            mapping = get_mapping_by_lsn(lsn)
        
        if not mapping:
            return False, None, f"ESN/LSN не найден в маппинге: ESN={esn}, LSN={lsn}"
        
        # Генерируем новое имя
        license_data['file_type'] = 'xml' if file_path.lower().endswith('.xml') else 'dat'
        new_filename = generate_new_filename(license_data, mapping)
        
        # Создаём целевую папку
        operator = mapping.get('operator')
        ne_type = mapping.get('ne_type')
        city = mapping.get('city')
        site = mapping.get('site')
        year = extract_year_from_valid_date(license_data.get('valid_date', 'UNKNOWN'))
        
        target_dir = os.path.join(target_folder, operator, ne_type, city, site, year)
        os.makedirs(target_dir, exist_ok=True)
        
        # Новый путь
        new_path = os.path.join(target_dir, new_filename)
        
        # Если файл уже существует, добавляем суффикс
        counter = 1
        original_new_path = new_path
        while os.path.exists(new_path):
            name, ext = os.path.splitext(original_new_path)
            new_path = f"{name}_v{counter}{ext}"
            counter += 1
        
        # Перемещаем и переименовываем
        shutil.move(file_path, new_path)
        
        logger.info(f"Переименован: {os.path.basename(file_path)} -> {new_filename}")
        
        return True, new_path, f"OK -> {new_filename}"
        
    except Exception as e:
        logger.error(f"Ошибка переименования {file_path}: {e}")
        return False, None, str(e)

def batch_rename_files(input_folder, target_folder, operator_name=None):
    """
    Пакетное переименование всех файлов в папке
    Возвращает: (success_list, fail_list)
    """
    if not os.path.exists(input_folder):
        return [], [{'filename': 'Папка не найдена', 'error': input_folder}]
    
    success = []
    failed = []
    
    files = [f for f in os.listdir(input_folder) 
             if f.lower().endswith('.xml') or f.lower().endswith('.dat')]
    
    for filename in files:
        file_path = os.path.join(input_folder, filename)
        result, new_path, message = rename_file_by_esn(file_path, target_folder)
        
        if result:
            success.append({
                'old_name': filename,
                'new_name': os.path.basename(new_path),
                'path': new_path,
                'message': message
            })
        else:
            failed.append({
                'filename': filename,
                'error': message
            })
    
    return success, failed