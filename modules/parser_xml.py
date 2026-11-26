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
        
        # ========== АГРЕГАЦИЯ РЕСУРСОВ (только из SaleInfo) ==========
        resources_dict = {}
        future_dates = []
        permanent_found = False
        raw_resources = []
        
        # Находим секцию SaleInfo
        sale_info = root.find('.//SaleInfo')
        if sale_info is None:
            logger.warning("Тег SaleInfo не найден, парсим все CapacityKey")
            search_root = root
        else:
            search_root = sale_info

        # Добавляем SPart (SaleItem) в ресурсы для агрегации
        for sales_item in sale_info.findall('.//SaleItem'):
            spart_name = sales_item.get('name')
            if not spart_name:
                continue
            
            for value_elem in sales_item.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                if spart_name not in resources_dict:
                    resources_dict[spart_name] = {
                        'name': spart_name,
                        'total_value': 0,
                        'permanent_value': 0,
                        'dated_values': [],
                        'latest_date': None,
                        'latest_value': 0
                    }
                
                entry = resources_dict[spart_name]
                entry['total_value'] += value
                
                if valid_date == 'PERMANENT':
                    entry['permanent_value'] += value
                    permanent_found = True
                elif valid_date not in ['UNKNOWN', '']:
                    entry['dated_values'].append({'date': valid_date, 'value': value})
                    future_dates.append(valid_date)
                    if entry['latest_date'] is None or valid_date > entry['latest_date']:
                        entry['latest_date'] = valid_date
                        entry['latest_value'] = value
        
        for cap_key in search_root.findall('.//CapacityKey'):
            name = cap_key.get('name')
            if not name:
                continue
            
            for value_elem in cap_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                raw_resources.append({
                    'name': name,
                    'value': value,
                    'valid_date': valid_date
                })
                
                if name not in resources_dict:
                    resources_dict[name] = {
                        'name': name,
                        'total_value': 0,
                        'permanent_value': 0,
                        'dated_values': [],
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
                    if entry['latest_date'] is None or valid_date > entry['latest_date']:
                        entry['latest_date'] = valid_date
                        entry['latest_value'] = value

        # Добавляем FeatureKey в ресурсы
        for feat_key in search_root.findall('.//FeatureKey'):
            name = feat_key.get('name')
            if not name:
                continue
            
            for value_elem in feat_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                # Сохраняем сырые данные
                raw_resources.append({
                    'name': name,
                    'value': value,
                    'valid_date': valid_date
                })
                
                if name not in resources_dict:
                    resources_dict[name] = {
                        'name': name,
                        'total_value': 0,
                        'permanent_value': 0,
                        'dated_values': [],
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
    result = {'sparts': [], 'orphan_bparts': []}
    
    sale_info = root.find('.//SaleInfo')
    if sale_info is None:
        logger.warning("Тег SaleInfo не найден")
        return result
    
    all_bparts = set()
    
    for sales_item in sale_info.findall('.//SaleItem'):
        spart_name = sales_item.get('name')
        if not spart_name:
            continue
        
        # Собираем ВСЕ значения Value
        values = sales_item.findall('Value')
        permanent_value = 0
        dated_value = 0
        dated_date = None
        
        for value_elem in values:
            valid_date = value_elem.get('validDate', 'UNKNOWN')
            try:
                value = int(value_elem.text.strip()) if value_elem.text else 0
            except (ValueError, AttributeError):
                value = 0
            
            if valid_date == 'PERMANENT':
                permanent_value = value
            elif valid_date not in ['UNKNOWN', '']:
                dated_value = value
                dated_date = valid_date
        
        # Общее значение и дата для обратной совместимости
        total_value = permanent_value + dated_value
        # Если есть датированная часть — показываем её дату, иначе PERMANENT
        if dated_date:
            spart_valid_date = dated_date
        elif permanent_value > 0:
            spart_valid_date = 'PERMANENT'
        else:
            spart_valid_date = 'UNKNOWN'
        
        bparts = []
        
        # CapacityKey внутри SaleItem
        for cap_key in sales_item.findall('.//CapacityKey'):
            name = cap_key.get('name')
            if not name:
                continue
            
            # Собираем все значения
            cap_permanent = 0
            cap_dated = 0
            cap_dated_date = None
            
            for value_elem in cap_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                if valid_date == 'PERMANENT':
                    cap_permanent = value
                elif valid_date not in ['UNKNOWN', '']:
                    cap_dated = value
                    cap_dated_date = valid_date
            
            cap_total = cap_permanent + cap_dated
            cap_date = cap_dated_date or ('PERMANENT' if cap_permanent > 0 else 'UNKNOWN')
            
            all_bparts.add(name)
            bparts.append({
                'name': name,
                'value': cap_total,
                'permanent_value': cap_permanent,
                'dated_value': cap_dated,
                'dated_date': cap_dated_date,
                'valid_date': cap_date
            })
        
        # FeatureKey внутри SaleItem — аналогично CapacityKey
        for feat_key in sales_item.findall('.//FeatureKey'):
            name = feat_key.get('name')
            if not name:
                continue
            
            feat_permanent = 0
            feat_dated = 0
            feat_dated_date = None
            
            for value_elem in feat_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                if valid_date == 'PERMANENT':
                    feat_permanent = value
                elif valid_date not in ['UNKNOWN', '']:
                    feat_dated = value
                    feat_dated_date = valid_date
            
            feat_total = feat_permanent + feat_dated
            feat_date = feat_dated_date or ('PERMANENT' if feat_permanent > 0 else 'UNKNOWN')
            
            all_bparts.add(name)
            bparts.append({
                'name': name,
                'value': feat_total,
                'permanent_value': feat_permanent,
                'dated_value': feat_dated,
                'dated_date': feat_dated_date,
                'valid_date': feat_date
            })
        
        result['sparts'].append({
            'name': spart_name,
            'value': total_value,
            'permanent_value': permanent_value,
            'dated_value': dated_value,
            'dated_date': dated_date,
            'valid_date': spart_valid_date,
            'bparts': bparts
        })
    
    # "Сироты" — аналогично
    for elem in sale_info:
        if elem.tag in ('CapacityKey', 'FeatureKey'):
            name = elem.get('name')
            if not name or name in all_bparts:
                continue
            
            orphan_permanent = 0
            orphan_dated = 0
            orphan_dated_date = None
            
            for value_elem in elem.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0
                
                if valid_date == 'PERMANENT':
                    orphan_permanent = value
                elif valid_date not in ['UNKNOWN', '']:
                    orphan_dated = value
                    orphan_dated_date = valid_date
            
            orphan_total = orphan_permanent + orphan_dated
            orphan_date = orphan_dated_date or ('PERMANENT' if orphan_permanent > 0 else 'UNKNOWN')
            
            result['orphan_bparts'].append({
                'name': name,
                'value': orphan_total,
                'permanent_value': orphan_permanent,
                'dated_value': orphan_dated,
                'dated_date': orphan_dated_date,
                'valid_date': orphan_date
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