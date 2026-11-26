"""
Парсер DAT файлов лицензий Huawei
Формат: ключ-значение, часто используется для бессрочных лицензий
Извлекает: LSN, ESN, Product, Version, CreateTime, Resource
Агрегирует одинаковые CapacityKey из разных секций
Сохраняет кэш для динамических полей
"""

import re
import json
from datetime import datetime
from modules.logger import get_logger

logger = get_logger(__name__)


def parse_dat_license(file_path):
    """
    Парсит DAT файл лицензии Huawei
    Возвращает словарь с данными лицензии и кэшем
    Агрегирует ресурсы из всех секций (Service, CGCAP, Trial0, etc.)
    """
    try:
        # Читаем файл с разными кодировками
        content = None
        used_encoding = None
        
        for encoding in ['utf-8', 'utf-16', 'cp1251', 'latin1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                used_encoding = encoding
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            logger.error(f"Не удалось прочитать файл (неизвестная кодировка): {file_path}")
            return None
        
        # Инициализируем результат
        result = {
            'lsn': None,
            'product': None,
            'version': None,
            'node': None,
            'esn': None,
            'create_time': None,
            'valid_date': 'PERMANENT',
            'resources': [],
            'file_type': 'dat',
            'file_path': file_path,
        }
        
        # Извлекаем LSN
        lsn_match = re.search(r'LicenseSerialNo[=:]\s*(\S+)', content, re.IGNORECASE)
        if lsn_match:
            result['lsn'] = lsn_match.group(1).strip()
        
        # Извлекаем CreateTime
        date_match = re.search(r'CreatedTime[=:]\s*([0-9\-\s:]+)', content, re.IGNORECASE)
        if date_match:
            result['create_time'] = date_match.group(1).strip()
        
        # Извлекаем ESN
        esn_match = re.search(r'Esn="([^"]+)"', content, re.IGNORECASE)
        if esn_match:
            result['esn'] = esn_match.group(1).strip()
        
        # Извлекаем Product (первый)
        product_match = re.search(r'Product=(\w+)', content, re.IGNORECASE)
        if product_match:
            result['product'] = product_match.group(1).strip()
        
        # Извлекаем Version
        version_match = re.search(r'Version=(\S+)', content, re.IGNORECASE)
        if version_match:
            result['version'] = version_match.group(1).strip()
        
        # Извлекаем Node
        node_match = re.search(r'Node=(\S+)', content, re.IGNORECASE)
        if node_match:
            result['node'] = node_match.group(1).strip()
        elif result['product']:
            result['node'] = result['product']
        
        # ========== АГРЕГАЦИЯ РЕСУРСОВ ИЗ ВСЕХ СЕКЦИЙ ==========
        # Разбиваем файл на блоки по "Product="
        sections = re.split(r'(?=^Product=)', content, flags=re.MULTILINE)
        
        resources_dict = {}
        future_dates = []
        permanent_found = False
        
        for section in sections:
            if not section.strip():
                continue
            
            # Извлекаем Feature
            feature_match = re.search(r'Feature=(\w+)', section)
            feature = feature_match.group(1) if feature_match else 'Unknown'
            
            resources_str = ""
            resource_match = re.search(r'Resource="([^"]+)"', section)
            if resource_match:
                resources_str = resource_match.group(1).strip()

            function_match = re.search(r'Function="([^"]+)"', section)
            if function_match:
                function_str = function_match.group(1).strip()
                if resources_str:
                    resources_str += ", " + function_str
                else:
                    resources_str = function_str

            if not resources_str:
                continue
            
            # Извлекаем Attrib для определения valid_date
            attrib_match = re.search(r'Attrib="([^"]+)"', section)
            is_permanent = False
            valid_date_str = None
            
            if attrib_match:
                attrib_parts = attrib_match.group(1).split(',')
                if len(attrib_parts) >= 2:
                    date_part = attrib_parts[1].strip()
                    if date_part.upper() == 'PERMANENT':
                        is_permanent = True
                        permanent_found = True
                    elif date_part != 'NULL' and date_part != '':
                        valid_date_str = date_part
                        future_dates.append(valid_date_str)
            
            # Парсим ресурсы из строки
            # Разделяем по запятой, но не разбиваем внутри кавычек
            items = []
            current = []
            in_quote = False
            
            for char in resources_str:
                if char == '"' and not in_quote:
                    in_quote = True
                    current.append(char)
                elif char == '"' and in_quote:
                    in_quote = False
                    current.append(char)
                elif char == ',' and not in_quote:
                    items.append(''.join(current).strip())
                    current = []
                else:
                    current.append(char)
            
            if current:
                items.append(''.join(current).strip())
            
            # Обрабатываем каждый ресурс
            for item in items:
                if '=' in item:
                    key, val = item.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    
                    # Убираем кавычки с значения
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    
                    try:
                        value = int(val)
                    except ValueError:
                        value = 0
                    
                    # Агрегируем
                    if key not in resources_dict:
                        resources_dict[key] = {
                            'name': key,
                            'total_value': 0,
                            'permanent_value': 0,
                            'dated_values': [],
                            'latest_date': None,
                            'latest_value': 0
                        }
                    
                    entry = resources_dict[key]
                    entry['total_value'] += value
                    
                    if is_permanent:
                        entry['permanent_value'] += value
                    elif valid_date_str:
                        entry['dated_values'].append({'date': valid_date_str, 'value': value})
                        if entry['latest_date'] is None or valid_date_str > entry['latest_date']:
                            entry['latest_date'] = valid_date_str
                            entry['latest_value'] = value
        
        # Формируем список ресурсов
        all_resources = []
        for key, data in resources_dict.items():
            all_resources.append({
                'name': key,
                'value': data['total_value'],
                'valid_date': data['latest_date'] or ('PERMANENT' if data['permanent_value'] > 0 else 'UNKNOWN'),
                'permanent_value': data['permanent_value'],
                'dated_values': json.dumps(data['dated_values']),
                'total_value': data['total_value'],
                'latest_date': data['latest_date'], 
                'latest_value': data['latest_value']  
            })
        
        result['resources'] = all_resources
        
        # Определяем общий valid_date
        if future_dates:
            result['valid_date'] = max(future_dates)
        elif permanent_found:
            result['valid_date'] = 'PERMANENT'
        else:
            result['valid_date'] = 'UNKNOWN'
        
        # Сохраняем кэш
        result['parsed_cache'] = {
            'file_type': 'dat',
            'file_path': file_path,
            'raw_content': content,
            'used_encoding': used_encoding,
            'resources': all_resources,
            'lsn': result['lsn'],
            'esn': result['esn'],
            'product': result['product'],
            'version': result['version'],
            'node': result['node'],
            'create_time': result['create_time'],
            'valid_date': result['valid_date']
        }
        
        logger.debug(f"Парсинг DAT: {file_path} -> {len(result['resources'])} ресурсов (агрегировано)")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка парсинга DAT {file_path}: {e}")
        return None


def extract_year_from_valid_date(valid_date):
    """
    Извлекает год из даты действия
    """
    if not valid_date:
        return 'unknown'
    
    if valid_date == 'PERMANENT':
        return 'permanent'
    
    try:
        date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d')
        return str(date_obj.year)
    except (ValueError, TypeError):
        match = re.search(r'(\d{4})', str(valid_date))
        return match.group(1) if match else 'unknown'