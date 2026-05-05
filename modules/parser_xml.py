"""
Парсер XML файлов лицензий Huawei
Поддерживает: UTF-8, UTF-16, CP1251, Latin1
Извлекает: LSN, ESN, Product, Version, Node, CreateTime, CapacityKey с validDate
Сохраняет кэш для динамических полей
"""

import xml.etree.ElementTree as ET
import re
from datetime import datetime
from modules.logger import get_logger

logger = get_logger(__name__)


def clean_xml_content(content):
    """
    Очищает XML от недопустимых символов и исправляет распространённые проблемы
    """
    # Удаляем недопустимые символы XML
    content = re.sub(r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]', '', content)
    
    # Исправляем самозакрывающиеся теги (если они без содержимого)
    content = re.sub(r'<(\w+)([^>]*)/>', r'<\1\2></\1>', content)
    
    # Удаляем BOM если есть
    if content.startswith('\ufeff'):
        content = content[1:]
    
    # Исправляем некорректные амперсанды
    content = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', content)
    
    return content


def try_parse_xml(content):
    """
    Пытается распарсить XML разными способами
    Возвращает корневой элемент или None
    """
    # Способ 1: Прямой парсинг
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        pass
    
    # Способ 2: Поиск корневого тега через regex
    root_match = re.search(r'<(\w+)[^>]*>.*</\1>', content, re.DOTALL)
    if root_match:
        try:
            return ET.fromstring(root_match.group(0))
        except ET.ParseError:
            pass
    
    # Способ 3: Пробуем найти любой тег
    tag_match = re.search(r'<(\w+)[^>]*>', content)
    if tag_match:
        try:
            # Оборачиваем в корневой элемент если нужно
            wrapped = f'<root>{content}</root>'
            root = ET.fromstring(wrapped)
            # Если есть дочерние элементы, возвращаем первый не root
            children = list(root)
            if children:
                return children[0]
        except ET.ParseError:
            pass
    
    return None


def parse_xml_license(file_path):
    """
    Парсит XML файл лицензии Huawei
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
        
        # 2. Очищаем содержимое
        content = clean_xml_content(content)
        
        # 3. Парсим XML
        root = try_parse_xml(content)
        if root is None:
            logger.error(f"Не удалось распарсить XML (невалидный формат): {file_path}")
            return None
        
        # 4. Инициализируем результат
        result = {
            'lsn': None,
            'product': None,
            'version': None,
            'node': None,
            'esn': None,
            'create_time': None,
            'valid_date': None,
            'resources': [],
            'file_type': 'xml',
            'file_path': file_path,
        }
        
        # 5. Извлекаем LSN
        lsn_elem = root.find('.//LSN')
        if lsn_elem is not None and lsn_elem.text:
            result['lsn'] = lsn_elem.text.strip()
        
        # 6. Извлекаем Product и Version
        offering = root.find('.//OfferingProduct')
        if offering is not None:
            result['product'] = offering.get('name', '')
            result['version'] = offering.get('version', '')
        
        # Альтернативный поиск Product
        if not result['product']:
            product_elem = root.find('.//Product')
            if product_elem is not None and product_elem.text:
                result['product'] = product_elem.text.strip()
        
        # 7. Извлекаем Node
        node_elem = root.find('.//Node')
        if node_elem is not None and node_elem.text:
            result['node'] = node_elem.text.strip()
        
        # 8. Извлекаем ESN
        esn_elem = root.find('.//ESN')
        if esn_elem is not None and esn_elem.text:
            result['esn'] = esn_elem.text.strip()
        
        # 9. Извлекаем CreateTime
        create_elem = root.find('.//CreateTime')
        if create_elem is not None and create_elem.text:
            result['create_time'] = create_elem.text.strip()
        
        # 10. Извлекаем все CapacityKey (ресурсы)
        all_valid_dates = []
        permanent_found = False
        
        for cap_key in root.findall('.//CapacityKey'):
            name = cap_key.get('name')
            if not name:
                continue
            
            for value_elem in cap_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                
                # Извлекаем значение
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                result['resources'].append({
                    'name': name,
                    'value': value,
                    'valid_date': valid_date
                })
                
                # Собираем даты для определения общего valid_date
                if valid_date not in ['UNKNOWN', 'PERMANENT']:
                    all_valid_dates.append(valid_date)
                elif valid_date == 'PERMANENT':
                    permanent_found = True
        
        # 11. Определяем общий valid_date (максимальная дата среди НЕ PERMANENT)
        # PERMANENT не должен влиять на valid_date - это бессрочная, но не дата
        future_dates = []
        permanent_found = False
        
        for res in result['resources']:
            valid_date = res.get('valid_date', '')
            if valid_date not in ['UNKNOWN', 'PERMANENT']:
                try:
                    # Проверяем, не истекла ли дата
                    date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d').date()
                    if date_obj >= datetime.now().date():
                        future_dates.append(valid_date)
                except:
                    future_dates.append(valid_date)
            elif valid_date == 'PERMANENT':
                permanent_found = True
        
        # Берём самую позднюю будущую дату
        if future_dates:
            latest = max(future_dates)
            result['valid_date'] = latest
        elif permanent_found:
            result['valid_date'] = 'PERMANENT'
        else:
            result['valid_date'] = 'UNKNOWN'
        
        # 12. Сохраняем кэш для динамических полей
        result['parsed_cache'] = {
            'file_type': 'xml',
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
        
        logger.debug(f"Парсинг XML: {file_path} -> {len(result['resources'])} ресурсов, valid_date={result['valid_date']}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка парсинга XML {file_path}: {e}")
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
        # Парсим дату формата YYYY-MM-DD
        date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d')
        return str(date_obj.year)
    except (ValueError, TypeError):
        # Пробуем другие форматы
        match = re.search(r'(\d{4})', str(valid_date))
        return match.group(1) if match else 'unknown'