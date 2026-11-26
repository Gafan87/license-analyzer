import os
import re
import shutil
from datetime import datetime
from modules.parser_xml import parse_xml_license
from modules.parser_dat import parse_dat_license
from modules.esn_mapper import get_mapping_by_esn, get_mapping_by_lsn
from modules.logger import get_logger
from modules.config_store import (
    render_license_basename,
    get_folder_structure_for_domain,
    get_license_name_template,
    render_license_basename,
)

logger = get_logger(__name__)


def extract_year_from_valid_date(valid_date):
    """Оставлено для обратной совместимости (используется в других местах)."""
    if valid_date == 'PERMANENT':
        return 'permanent'
    try:
        date_obj = datetime.strptime(valid_date[:10], '%Y-%m-%d')
        return str(date_obj.year)
    except Exception:
        match = re.search(r'(\d{4})', valid_date or '')
        return match.group(1) if match else 'unknown'


def _normalize_version(v):
    if not v: return 'unknown'
    v = str(v).strip().upper()
    import re
    # Ищем 'R' и любые цифры после нее
    m = re.search(r'R(\d+)', v)
    if m: return f'R{int(m.group(1)):02d}'
    # Если это просто число
    if v.isdigit(): return f'R{int(v):02d}'
    return v

def _build_new_path(remote_base, license_data, mapping):
    from modules.config_store import get_folder_structure_for_domain, get_license_name_template, render_license_basename
    operator = mapping.get('operator') or 'Unknown'
    domain = mapping.get('domain') or 'Unknown'

    path_values = {
        'operator': operator,
        'domain': domain,
        'sub_domain': mapping.get('sub_domain') or '',
        'ne_type': mapping.get('ne_type') or 'Unknown',
        'city': mapping.get('city') or 'Unknown',
        'city_full': str(mapping.get('city_full') or mapping.get('city') or 'Unknown').title(),
        'site': mapping.get('site') or 'Unknown',
        'year': license_data.get('year') or '',
        'version': _normalize_version(license_data.get('version')),
        'lsn': license_data.get('lsn') or '',
        'esn': license_data.get('esn') or '',
    }

    from modules.bulk_reorganizer import _render_folder_segment
    levels = get_folder_structure_for_domain(domain, operator=operator, has_sub_domain=bool(mapping.get('sub_domain')))
    parts = [_render_folder_segment(level, path_values) for level in levels]

    # Генерация имени через шаблон (с учетом домена)
    template = get_license_name_template(domain, operator=operator)
    base_name = render_license_basename(template, path_values)
    base_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base_name)
    base_name = re.sub(r'\s{2,}', ' ', base_name)
    base_name = re.sub(r'_{2,}', '_', base_name).strip(' _-.')
    ext = license_data.get('file_type', 'dat').lower()
    new_filename = f"{base_name}.{ext}"

    import os
    new_path = os.path.join(remote_base, operator, *parts, new_filename)
    return new_path, new_filename


def rename_file_by_esn(file_path, target_folder, mapping_db=None):
    """
    Переименовывает файл по ESN и перемещает в целевую папку по правилам из config.json.
    Возвращает: (success, new_path, message)
    """
    try:
        if file_path.lower().endswith('.xml'):
            license_data = parse_xml_license(file_path)
        else:
            license_data = parse_dat_license(file_path)

        if not license_data:
            return False, None, "Не удалось распарсить файл"

        esn = license_data.get('esn')
        lsn = license_data.get('lsn')

        mapping = None
        if esn:
            mapping = get_mapping_by_esn(esn)
        if not mapping and lsn:
            mapping = get_mapping_by_lsn(lsn)

        if not mapping:
            return False, None, f"ESN/LSN не найден в маппинге: ESN={esn}, LSN={lsn}"

        license_data['file_type'] = 'xml' if file_path.lower().endswith('.xml') else 'dat'
        new_path, new_filename = _build_new_path(target_folder, license_data, mapping)

        os.makedirs(os.path.dirname(new_path), exist_ok=True)

        # Если файл уже существует — суффикс
        counter = 1
        original_new_path = new_path
        while os.path.exists(new_path):
            name, ext = os.path.splitext(original_new_path)
            new_path = f"{name}_v{counter}{ext}"
            counter += 1

        shutil.move(file_path, new_path)
        logger.info(f"Переименован: {os.path.basename(file_path)} -> {os.path.basename(new_path)}")

        return True, new_path, f"OK -> {os.path.basename(new_path)}"

    except Exception as e:
        logger.error(f"Ошибка переименования {file_path}: {e}")
        return False, None, str(e)


def batch_rename_files(input_folder, target_folder, operator_name=None):
    """Пакетное переименование всех файлов в папке."""
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
                'message': message,
            })
        else:
            failed.append({'filename': filename, 'error': message})

    return success, failed