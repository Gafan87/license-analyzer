"""
Парсер XML файлов лицензий Huawei
Поддерживает: UTF-8, UTF-16, CP1251, Latin1
Извлекает: LSN, ESN, Product, Version, Node, CreateTime, CapacityKey с validDate
Агрегирует одинаковые CapacityKey с разными датами
Сохраняет кэш для динамических полей
"""

import xml.etree.ElementTree as ET
import re
import json
from datetime import datetime
from modules.logger import get_logger

logger = get_logger(__name__)


def clean_xml_content(content):
    """
    Очищает XML от недопустимых символов и исправляет распространённые проблемы
    """
    content = re.sub(r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]', '', content)
    content = re.sub(r'<(\w+)([^>]*)/>', r'<\1\2></\1>', content)
    if content.startswith('\ufeff'):
        content = content[1:]
    content = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', content)
    return content


def try_parse_xml(content):
    """
    Пытается распарсить XML разными способами
    """
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        pass
    
    root_match = re.search(r'<(\w+)[^>]*>.*</\1>', content, re.DOTALL)
    if root_match:
        try:
            return ET.fromstring(root_match.group(0))
        except ET.ParseError:
            pass
    
    tag_match = re.search(r'<(\w+)[^>]*>', content)
    if tag_match:
        try:
            wrapped = f'<root>{content}</root>'
            root = ET.fromstring(wrapped)
            children = list(root)
            if children:
                return children[0]
        except ET.ParseError:
            pass
    
    return None


def parse_xml_license(file_path):
    """
    Парсит XML файл лицензии Huawei
    Возвращает словарь с данными лицензии и кэшем
    Агрегирует одинаковые CapacityKey с суммированием значений
    """
    try:
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
        
        content = clean_xml_content(content)
        root = try_parse_xml(content)
        if root is None:
            logger.error(f"Не удалось распарсить XML (невалидный формат): {file_path}")
            return None
        
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
        
        # Извлекаем LSN
        lsn_elem = root.find('.//LSN')
        if lsn_elem is not None and lsn_elem.text:
            result['lsn'] = lsn_elem.text.strip()
        
        # Извлекаем Product и Version
        offering = root.find('.//OfferingProduct')
        if offering is not None:
            result['product'] = offering.get('name', '')
            result['version'] = offering.get('version', '')
        
        if not result['product']:
            product_elem = root.find('.//Product')
            if product_elem is not None and product_elem.text:
                result['product'] = product_elem.text.strip()
        
        # Извлекаем Node
        node_elem = root.find('.//Node')
        if node_elem is not None and node_elem.text:
            result['node'] = node_elem.text.strip()
        
        # Извлекаем ESN
        esn_elem = root.find('.//ESN')
        if esn_elem is not None and esn_elem.text:
            result['esn'] = esn_elem.text.strip()
        
        # Извлекаем CreateTime
        create_elem = root.find('.//CreateTime')
        if create_elem is not None and create_elem.text:
            result['create_time'] = create_elem.text.strip()
        
        # ========== АГРЕГАЦИЯ РЕСУРСОВ ==========
        resources_dict = {}
        future_dates = []
        permanent_found = False
        raw_resources = []  # для отладки
        
        for cap_key in root.findall('.//CapacityKey'):
            name = cap_key.get('name')
            if not name:
                continue
            
            for value_elem in cap_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                # Сохраняем сырые данные для отладки (опционально)
                raw_resources.append({
                    'name': name,
                    'value': value,
                    'valid_date': valid_date
                })
                
                # Инициализируем запись для ключа
                if name not in resources_dict:
                    resources_dict[name] = {
                        'name': name,
                        'total_value': 0,
                        'permanent_value': 0,
                        'dated_values': [],  # список {date: value}
                        'latest_date': None,
                        'latest_value': 0
                    }
                
                entry = resources_dict[name]
                entry['total_value'] += value
                
                if valid_date == 'PERMANENT':
                    entry['permanent_value'] += value
                    permanent_found = True
                elif valid_date not in ['UNKNOWN', '']:
                    entry['dated_values'].append({'date': valid_date, 'value': value})
                    future_dates.append(valid_date)
                    # Обновляем самую позднюю дату
                    if entry['latest_date'] is None or valid_date > entry['latest_date']:
                        entry['latest_date'] = valid_date
                        entry['latest_value'] = value
        
        # Формируем список ресурсов с агрегированными данными
        all_resources = []
        for key, data in resources_dict.items():
            all_resources.append({
                'name': key,
                'value': data['total_value'],  # суммарное значение для обратной совместимости
                'valid_date': data['latest_date'] or ('PERMANENT' if data['permanent_value'] > 0 else 'UNKNOWN'),
                'permanent_value': data['permanent_value'],
                'dated_values': json.dumps(data['dated_values']),
                'total_value': data['total_value'],
                'latest_date': data['latest_date'],
                'latest_value': data['latest_value']
            })
        
        result['resources'] = all_resources
        
        # Определяем общий valid_date лицензии (самая поздняя дата среди всех ресурсов)
        if future_dates:
            result['valid_date'] = max(future_dates)
        elif permanent_found:
            result['valid_date'] = 'PERMANENT'
        else:
            result['valid_date'] = 'UNKNOWN'
        
        # Сохраняем кэш
        result['parsed_cache'] = {
            'file_type': 'xml',
            'file_path': file_path,
            'raw_content': content,
            'used_encoding': used_encoding,
            'resources': all_resources,
            'resources_raw': raw_resources,  # оригинальные данные (опционально)
            'lsn': result['lsn'],
            'esn': result['esn'],
            'product': result['product'],
            'version': result['version'],
            'node': result['node'],
            'create_time': result['create_time'],
            'valid_date': result['valid_date']
        }
        
        logger.debug(f"Парсинг XML: {file_path} -> {len(result['resources'])} ресурсов (агрегировано), valid_date={result['valid_date']}")
        
        # Извлекаем иерархию SPart/BPart
        hierarchy = extract_spart_hierarchy(root)
        result['spart_hierarchy'] = hierarchy
        
        # Сохраняем в parsed_cache
        result['parsed_cache']['spart_hierarchy'] = hierarchy
        return result
        
    except Exception as e:
        logger.error(f"Ошибка парсинга XML {file_path}: {e}")
        return None

def extract_spart_hierarchy(root):
    """
    Извлекает иерархическую структуру SPart (SalesItem) и BPart (CapacityKey/FeatureKey)
    Возвращает:
    {
        'sparts': [
            {
                'name': 'SF4SMBVOISW02',
                'value': 100,
                'valid_date': '2028-03-01',
                'bparts': [
                    {'name': 'LCF4REGUSR01', 'value': 500, 'valid_date': '2028-03-01'},
                    {'name': 'LCF4BASESW01', 'value': 2, 'valid_date': 'PERMANENT'}
                ]
            }
        ],
        'orphan_bparts': []  # CapacityKey не входящие ни в один SalesItem
    }
    """
    result = {'sparts': [], 'orphan_bparts': []}
    
    # Находим все SalesItem (SPart)
    sales_items = root.findall('.//SalesItem')
    
    # Собираем все CapacityKey/FeatureKey, чтобы потом найти "сирот"
    all_bparts = set()
    
    for sales_item in sales_items:
        spart_name = sales_item.get('name')
        if not spart_name:
            continue
        
        # Значение SPart (value атрибут)
        spart_value_str = sales_item.get('value', '0')
        try:
            spart_value = int(spart_value_str)
        except:
            spart_value = 0
        
        spart_valid_date = sales_item.get('validDate', 'UNKNOWN')
        
        bparts = []
        
        # Ищем CapacityKey внутри SalesItem
        for cap_key in sales_item.findall('.//CapacityKey'):
            name = cap_key.get('name')
            if not name:
                continue
            all_bparts.add(name)
            
            value_str = cap_key.get('value', '0')
            try:
                value = int(value_str)
            except:
                value = 0
            
            valid_date = cap_key.get('validDate', 'UNKNOWN')
            
            bparts.append({
                'name': name,
                'value': value,
                'valid_date': valid_date
            })
        
        # Ищем FeatureKey внутри SalesItem
        for feat_key in sales_item.findall('.//FeatureKey'):
            name = feat_key.get('name')
            if not name:
                continue
            all_bparts.add(name)
            
            value_str = feat_key.get('value', '0')
            try:
                value = int(value_str)
            except:
                value = 0
            
            valid_date = feat_key.get('validDate', 'UNKNOWN')
            
            bparts.append({
                'name': name,
                'value': value,
                'valid_date': valid_date
            })
        
        result['sparts'].append({
            'name': spart_name,
            'value': spart_value,
            'valid_date': spart_valid_date,
            'bparts': bparts
        })
    
    # Теперь найдём все CapacityKey/FeatureKey, которые не входят ни в один SalesItem
    all_keys = root.findall('.//CapacityKey') + root.findall('.//FeatureKey')
    for key in all_keys:
        name = key.get('name')
        if not name:
            continue
        
        # Проверяем, есть ли этот ключ в каком-либо SPart
        found = False
        for spart in result['sparts']:
            for bpart in spart['bparts']:
                if bpart['name'] == name:
                    found = True
                    break
            if found:
                break
        
        if not found:
            value_str = key.get('value', '0')
            try:
                value = int(value_str)
            except:
                value = 0
            valid_date = key.get('validDate', 'UNKNOWN')
            result['orphan_bparts'].append({
                'name': name,
                'value': value,
                'valid_date': valid_date
            })
    
    return result

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