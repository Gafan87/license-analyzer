import os
import re
import shutil
import hashlib
from datetime import datetime
from modules.logger import get_logger
from modules.config_store import (
    get_folder_structure_for_domain,
    get_license_name_template,
    render_license_basename,
)

logger = get_logger(__name__)


def ensure_remote_path(remote_base, operator, ne_type, city, site, year_folder):
    """Оставлено для совместимости. Строит путь по старой схеме — не рекомендуется."""
    remote_path = os.path.join(remote_base, operator or 'Unknown', ne_type or 'Unknown',
                               city or 'Unknown', site or 'Unknown', year_folder or 'permanent')
    os.makedirs(remote_path, exist_ok=True)
    return remote_path


def move_to_old_folder(remote_file_path):
    file_dir = os.path.dirname(remote_file_path)
    old_dir = os.path.join(file_dir, 'old')
    os.makedirs(old_dir, exist_ok=True)
    filename = os.path.basename(remote_file_path)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    old_file_path = os.path.join(old_dir, f"{timestamp}_{filename}")
    shutil.move(remote_file_path, old_file_path)
    logger.info(f"Старая версия перемещена: {old_file_path}")
    return old_file_path


def file_needs_update(local_hash, remote_path):
    if not os.path.exists(remote_path):
        return True
    hasher = hashlib.md5()
    with open(remote_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return local_hash != hasher.hexdigest()


def _calc_year_folder(license_info):
    valid_date = license_info.get('valid_date', '')
    year_folder = license_info.get('year', 'permanent')
    if valid_date and valid_date not in ('PERMANENT', 'UNKNOWN'):
        m = re.match(r'(\d{4})-(\d{2})', valid_date)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            year_folder = str(year - 1) if month <= 3 else str(year)
    return year_folder


def generate_license_filename(license_info):
    """
    Совместимая сигнатура. Возвращает (filename, year_folder) по новым правилам.
    Использует config.json → license_name_template.
    """
    year_folder = _calc_year_folder(license_info)
    domain = license_info.get('domain') or 'Unknown'
    template = get_license_name_template()
    base = render_license_basename(template, {
        'operator': license_info.get('operator') or '',
        'domain': domain,
        'ne_type': license_info.get('ne_type') or '',
        'city': license_info.get('city') or '',
        'site': license_info.get('site') or '',
        'year': year_folder,
        'version': license_info.get('version') or '',
        'lsn': license_info.get('lsn') or '',
        'esn': license_info.get('esn') or '',
        'create_time': license_info.get('create_time') or '',
    })
    base = re.sub(r'[^\w\-.]', '_', base)

    ext = '.xml' if (license_info.get('filename') or '').lower().endswith('.xml') else '.dat'
    return base + ext, year_folder


def _build_remote_path(remote_base, license_info):
    """Строит полный путь на шаре по config.json."""
    domain = license_info.get('domain') or 'Unknown'
    year_folder = _calc_year_folder(license_info)

    path_values = {
        'operator': license_info.get('operator') or 'Unknown',
        'domain': domain,
        'ne_type': license_info.get('ne_type') or 'Unknown',
        'city': license_info.get('city') or 'Unknown',
        'site': license_info.get('site') or 'Unknown',
        'year': year_folder,
        'version': license_info.get('version') or 'unknown',
        'lsn': license_info.get('lsn') or '',
        'esn': license_info.get('esn') or '',
    }

    levels = get_folder_structure_for_domain(domain)
    parts = [re.sub(r'[^\w\-.]', '_', str(path_values.get(lvl, 'Unknown')) or 'Unknown')
             for lvl in levels]

    filename, _ = generate_license_filename(license_info)
    return os.path.join(remote_base, *parts, filename)


def sync_license_to_remote(license_info, remote_base, modified_by='system'):
    try:
        local_path = license_info.get('local_path') or ''
        file_hash = license_info.get('file_hash') or ''

        remote_file_path = _build_remote_path(remote_base, license_info)
        remote_dir = os.path.dirname(remote_file_path)
        os.makedirs(remote_dir, exist_ok=True)

        if not local_path or not os.path.exists(local_path):
            logger.warning(f"local_path пуст для {os.path.basename(remote_file_path)}, пропускаем копирование")
            return True

        if os.path.exists(remote_file_path) and file_hash:
            hasher = hashlib.md5()
            with open(remote_file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            if hasher.hexdigest() == file_hash:
                logger.debug(f"Файл не изменился: {os.path.basename(remote_file_path)}")
                return True

        if os.path.exists(remote_file_path):
            old_dir = os.path.join(remote_dir, 'old')
            os.makedirs(old_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            old_path = os.path.join(old_dir, f"{timestamp}_{os.path.basename(remote_file_path)}")
            shutil.move(remote_file_path, old_path)
            logger.info(f"Старая версия перемещена: {old_path}")

        shutil.copy2(local_path, remote_file_path)
        logger.info(f"Файл скопирован: {os.path.basename(remote_file_path)} -> {remote_file_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка синхронизации {license_info.get('filename', 'unknown')}: {e}")
        return False


def sync_all_licenses(licenses, remote_base, modified_by='system'):
    success_count = 0
    fail_count = 0
    for lic in licenses:
        if sync_license_to_remote(lic, remote_base, modified_by):
            success_count += 1
        else:
            fail_count += 1
    logger.info(f"Синхронизация завершена: успешно {success_count}, ошибок {fail_count}")
    return success_count, fail_count


def download_db_from_remote(network_db_path, local_db_path):
    if not os.path.exists(network_db_path):
        logger.warning(f"Удалённая БД не найдена: {network_db_path}")
        return False
    try:
        shutil.copy2(network_db_path, local_db_path)
        return True
    except Exception as e:
        logger.error(f"Ошибка скачивания БД: {e}")
        return False


def upload_db_to_remote(local_db_path, network_db_path):
    if not os.path.exists(local_db_path):
        return False
    try:
        os.makedirs(os.path.dirname(network_db_path), exist_ok=True)
        shutil.copy2(local_db_path, network_db_path)
        return True
    except Exception as e:
        logger.error(f"Ошибка загрузки БД: {e}")
        return False