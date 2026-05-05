"""
Парсер DAT файлов лицензий Huawei
Формат: ключ-значение, часто используется для бессрочных лицензий
Извлекает: LSN, ESN, Product, Version, CreateTime, Resource
Сохраняет кэш для динамических полей
"""

import re
from datetime import datetime
from modules.logger import get_logger

logger = get_logger(__name__)


def parse_dat_license(file_path):
    """
    Парсит DAT файл лицензии Huawei
    Возвращает словарь с данными лицензии и кэшем для динамических полей
    """
    try:
        # 1. Читаем файл с разными кодировками
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
        
        # 2. Инициализируем результат
        result = {
            'lsn': None,
            'product': None,
            'version': None,
            'node': None,
            'esn': None,
            'create_time': None,
            'valid_date': 'PERMANENT',  # DAT обычно бессрочные
            'resources': [],
            'file_type': 'dat',
            'file_path': file_path,
        }
        
        # 3. Извлекаем LSN (LicenseSerialNo)
        lsn_match = re.search(r'LicenseSerialNo[=:]\s*(\S+)', content, re.IGNORECASE)
        if lsn_match:
            result['lsn'] = lsn_match.group(1).strip()
        
        # 4. Извлекаем CreateTime (CreatedTime)
        date_match = re.search(r'CreatedTime[=:]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})', content, re.IGNORECASE)
        if date_match:
            result['create_time'] = date_match.group(1).strip()
        else:
            # Альтернативный формат без времени
            date_match = re.search(r'CreatedTime[=:]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', content, re.IGNORECASE)
            if date_match:
                result['create_time'] = date_match.group(1).strip()
        
        # 5. Извлекаем Product
        product_match = re.search(r'Product[=:]\s*(\S+)', content, re.IGNORECASE)
        if product_match:
            result['product'] = product_match.group(1).strip()
        
        # 6. Извлекаем Version
        version_match = re.search(r'Version[=:]\s*(\S+)', content, re.IGNORECASE)
        if version_match:
            result['version'] = version_match.group(1).strip()
        
        # 7. Извлекаем ESN
        esn_match = re.search(r'Esn[=:]\s*"?([^"\n]+)"?', content, re.IGNORECASE)
        if esn_match:
            result['esn'] = esn_match.group(1).strip()
        
        # 8. Извлекаем Node (может называться Product или Node)
        node_match = re.search(r'Node[=:]\s*(\S+)', content, re.IGNORECASE)
        if node_match:
            result['node'] = node_match.group(1).strip()
        elif not result['node'] and result['product']:
            result['node'] = result['product']
        
        # 9. Извлекаем Resource (формат: KEY1=1000, KEY2=2000 или "KEY1=1000,KEY2=2000")
        resource_match = re.search(r'Resource[=:]\s*"?([^"\n]+)"?', content, re.IGNORECASE)
        
        if resource_match:
            resources_str = resource_match.group(1).strip()
            
            # Разбираем ресурсы (могут быть разделены запятыми или пробелами)
            # Убираем кавычки если есть
            resources_str = resources_str.strip('"\'')
            
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
            
            # Парсим каждый item (формат: KEY=VALUE)
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
                    
                    result['resources'].append({
                        'name': key,
                        'value': value,
                        'valid_date': 'PERMANENT'  # DAT ресурсы всегда PERMANENT
                    })
        
        # 10. Проверяем наличие PERMANENT в ресурсах
        if result['resources']:
            permanent_count = sum(1 for r in result['resources'] if r['valid_date'] == 'PERMANENT')
            logger.debug(f"DAT ресурсы: {len(result['resources'])} всего, {permanent_count} PERMANENT")
        
        # 11. Сохраняем кэш для динамических полей
        result['parsed_cache'] = {
            'file_type': 'dat',
            'file_path': file_path,
            'raw_content': content,
            'used_encoding': used_encoding,
            'resources': result['resources'].copy(),
            'lsn': result['lsn'],
            'esn': result['esn'],
            'product': result['product'],
            'version': result['version'],
            'node': result['node'],
            'create_time': result['create_time'],
            'valid_date': result['valid_date']
        }
        
        logger.debug(f"Парсинг DAT: {file_path} -> {len(result['resources'])} ресурсов")
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