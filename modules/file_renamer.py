import os
import re
import shutil
from datetime import datetime
from modules.parser_xml import parse_xml_license
from modules.parser_dat import parse_dat_license
from modules.esn_mapper import get_mapping_by_esn, get_mapping_by_lsn
from modules.logger import get_logger
from modules.config_store import (
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


def _build_new_path(remote_base, license_data, mapping):
    """
    Возвращает (new_path, new_filename) по настройкам из config.json.
    folder_structure берётся по domain (или default), имя — по license_name_template.
    Расширение — из исходного файла (file_type).
    """
    operator = mapping.get('operator') or 'Unknown'
    domain = mapping.get('domain') or 'Unknown'

    # Значения для подстановок в структуру папок
    path_values = {
        'operator': operator,
        'domain': domain,
        'ne_type': mapping.get('ne_type') or 'Unknown',
        'city': mapping.get('city') or 'Unknown',
        'site': mapping.get('site') or 'Unknown',
        'year': license_data.get('year') or extract_year_from_valid_date(license_data.get('valid_date', 'UNKNOWN')),
        'version': license_data.get('version') or 'unknown',
        'lsn': license_data.get('lsn') or '',
        'esn': license_data.get('esn') or '',
    }

    # Путь: по структуре для домена
    levels = get_folder_structure_for_domain(domain)
    parts = []
    for level in levels:
        val = path_values.get(level, '')
        # sanitize каждый сегмент пути
        val = re.sub(r'[^\w\-.]', '_', str(val)) if val else 'Unknown'
        parts.append(val)
    target_dir = os.path.join(remote_base, *parts)

    # Имя файла: по шаблону, без расширения
    template = get_license_name_template()
    base_name = render_license_basename(template, {
        **path_values,
        'create_time': license_data.get('create_time', ''),
    })
    # sanitize, но оставляем точки (вдруг в шаблоне пользователь сам вставит)
    base_name = re.sub(r'[^\w\-.]', '_', base_name)

    # Расширение — из исходного файла
    ext = '.xml' if license_data.get('file_type') == 'xml' else '.dat'
    new_filename = base_name + ext

    new_path = os.path.join(target_dir, new_filename)
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