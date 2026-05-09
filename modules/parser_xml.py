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
    Извлекает Spart (SaleItem) и их Bpart (CapacityKey/FeatureKey)
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

        # ========== ОСНОВНЫЕ ПОЛЯ ==========
        # LSN
        lsn_elem = root.find('.//LSN')
        if lsn_elem is not None and lsn_elem.text:
            result['lsn'] = lsn_elem.text.strip()

        # Product и Version
        offering = root.find('.//OfferingProduct')
        if offering is not None:
            result['product'] = offering.get('name', '')
            result['version'] = offering.get('version', '')

        if not result['product']:
            product_elem = root.find('.//Product')
            if product_elem is not None and product_elem.text:
                result['product'] = product_elem.text.strip()

        # Node
        node_elem = root.find('.//Node')
        if node_elem is not None and node_elem.text:
            result['node'] = node_elem.text.strip()

        # ESN
        esn_elem = root.find('.//ESN')
        if esn_elem is not None and esn_elem.text:
            result['esn'] = esn_elem.text.strip()

        # CreateTime
        create_elem = root.find('.//CreateTime')
        if create_elem is not None and create_elem.text:
            result['create_time'] = create_elem.text.strip()

        # ========== АГРЕГАЦИЯ РЕСУРСОВ ИЗ KeyInfo ==========
        resources_dict = {}
        future_dates = []
        permanent_found = False

        # Собираем все CapacityKey из KeyInfo (обычные ресурсы)
        for cap_key in root.findall('.//KeyInfo/CapacityKey'):
            name = cap_key.get('name')
            if not name:
                continue

            for value_elem in cap_key.findall('Value'):
                valid_date = value_elem.get('validDate', 'UNKNOWN')
                try:
                    value = int(value_elem.text.strip()) if value_elem.text else 0
                except (ValueError, AttributeError):
                    value = 0

                if name not in resources_dict:
                    resources_dict[name] = {
                        'name': name,
                        'total_value': 0,
                        'permanent_value': 0,
                        'dated_values': [],
                        'latest_date': None,
                        'latest_value': 0,
                        'is_spart': False,
                        'is_bpart': False,
                        'parent_spart': None
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

        # ========== ИЗВЛЕЧЕНИЕ SPART (SaleItem) И ИХ BPART ==========
        spart_resources = []
        bpart_keys_set = set()

        for sale_item in root.findall('.//SaleItem'):
            spart_name = sale_item.get('name')
            if not spart_name:
                continue

            # Значение Spart
            spart_value = 0
            spart_valid_date = 'UNKNOWN'
            value_elem = sale_item.find('Value')
            if value_elem is not None:
                try:
                    spart_value = int(value_elem.text.strip()) if value_elem.text else 0
                except:
                    spart_value = 0
                spart_valid_date = value_elem.get('validDate', 'UNKNOWN')

            # Описание Spart
            desc_elem = sale_item.find('DesEng')
            spart_description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ''
            spart_unit = desc_elem.get('unit', '') if desc_elem is not None else ''

            # Собираем дочерние Bpart
            child_keys = []
            for cap_key in sale_item.findall('.//CapacityKey'):
                child_name = cap_key.get('name')
                if child_name:
                    child_keys.append(child_name)
                    bpart_keys_set.add(child_name)

            for feat_key in sale_item.findall('.//FeatureKey'):
                child_name = feat_key.get('name')
                if child_name:
                    child_keys.append(child_name)
                    bpart_keys_set.add(child_name)

            spart_resources.append({
                'name': spart_name,
                'value': spart_value,
                'valid_date': spart_valid_date,
                'is_spart': True,
                'is_bpart': False,
                'child_keys': child_keys,
                'description': spart_description,
                'unit': spart_unit
            })

            # Добавляем Spart в общий словарь (если его там нет)
            if spart_name not in resources_dict:
                resources_dict[spart_name] = {
                    'name': spart_name,
                    'total_value': spart_value,
                    'permanent_value': spart_value if spart_valid_date == 'PERMANENT' else 0,
                    'dated_values': [{'date': spart_valid_date, 'value': spart_value}] if spart_valid_date not in ['PERMANENT', 'UNKNOWN'] else [],
                    'latest_date': spart_valid_date if spart_valid_date not in ['PERMANENT', 'UNKNOWN'] else None,
                    'latest_value': spart_value,
                    'is_spart': True,
                    'is_bpart': False,
                    'parent_spart': None
                }

        # ========== ОБНОВЛЕНИЕ BPART В СЛОВАРЕ ==========
        for key, data in resources_dict.items():
            if key in bpart_keys_set:
                data['is_bpart'] = True

        # ========== ОПРЕДЕЛЕНИЕ ВАЛИДНОЙ ДАТЫ ДЛЯ SPART ==========
        # Для Spart, которые имеют Bpart, суммируем значения Bpart
        for spart in spart_resources:
            if spart['child_keys']:
                total = 0
                permanent_total = 0
                dated_values = []
                latest_date = None
                latest_value = 0

                for child_key in spart['child_keys']:
                    if child_key in resources_dict:
                        child_data = resources_dict[child_key]
                        total += child_data['total_value']
                        permanent_total += child_data['permanent_value']
                        for dv in child_data['dated_values']:
                            dated_values.append(dv)
                            if latest_date is None or dv['date'] > latest_date:
                                latest_date = dv['date']
                                latest_value = dv['value']

                if total > 0:
                    resources_dict[spart['name']]['total_value'] = total
                    resources_dict[spart['name']]['permanent_value'] = permanent_total
                    resources_dict[spart['name']]['dated_values'] = dated_values
                    resources_dict[spart['name']]['latest_date'] = latest_date
                    resources_dict[spart['name']]['latest_value'] = latest_value

        # ========== ФОРМИРОВАНИЕ ИТОГОВОГО СПИСКА РЕСУРСОВ ==========
        all_resources = []
        processed_keys = set()

        # Сначала добавляем Spart
        for spart in spart_resources:
            all_resources.append({
                'name': spart['name'],
                'value': resources_dict[spart['name']]['total_value'],
                'valid_date': resources_dict[spart['name']]['latest_date'] or ('PERMANENT' if resources_dict[spart['name']]['permanent_value'] > 0 else 'UNKNOWN'),
                'is_spart': True,
                'is_bpart': False,
                'child_keys': spart['child_keys'],
                'description': spart.get('description', ''),
                'unit': spart.get('unit', ''),
                'permanent_value': resources_dict[spart['name']]['permanent_value'],
                'dated_values': json.dumps(resources_dict[spart['name']]['dated_values']),
                'total_value': resources_dict[spart['name']]['total_value']
            })
            processed_keys.add(spart['name'])

        # Затем добавляем Bpart и обычные ресурсы
        for key, data in resources_dict.items():
            if key in processed_keys:
                continue

            all_resources.append({
                'name': key,
                'value': data['total_value'],
                'valid_date': data['latest_date'] or ('PERMANENT' if data['permanent_value'] > 0 else 'UNKNOWN'),
                'is_spart': False,
                'is_bpart': data.get('is_bpart', False),
                'child_keys': [],
                'description': '',
                'unit': '',
                'permanent_value': data['permanent_value'],
                'dated_values': json.dumps(data['dated_values']),
                'total_value': data['total_value']
            })

        result['resources'] = all_resources

        # ========== ОПРЕДЕЛЕНИЕ ОБЩЕЙ ДАТЫ ДЕЙСТВИЯ ЛИЦЕНЗИИ ==========
        if future_dates:
            result['valid_date'] = max(future_dates)
        elif permanent_found:
            result['valid_date'] = 'PERMANENT'
        else:
            result['valid_date'] = 'UNKNOWN'

        # ========== СОХРАНЕНИЕ КЭША ==========
        result['parsed_cache'] = {
            'file_type': 'xml',
            'file_path': file_path,
            'raw_content': content,
            'used_encoding': used_encoding,
            'resources': all_resources,
            'spart_resources': spart_resources,
            'bpart_keys': list(bpart_keys_set),
            'lsn': result['lsn'],
            'esn': result['esn'],
            'product': result['product'],
            'version': result['version'],
            'node': result['node'],
            'create_time': result['create_time'],
            'valid_date': result['valid_date']
        }

        logger.debug(f"Парсинг XML: {file_path} -> {len(result['resources'])} ресурсов (агрегировано), valid_date={result['valid_date']}")
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
        date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d')
        return str(date_obj.year)
    except (ValueError, TypeError):
        match = re.search(r'(\d{4})', str(valid_date))
        return match.group(1) if match else 'unknown'