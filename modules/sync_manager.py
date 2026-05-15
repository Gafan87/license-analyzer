import os
import shutil
from datetime import datetime
from modules.logger import get_logger
from modules.database import save_license, get_connection

logger = get_logger(__name__)

def ensure_remote_path(remote_base, operator, ne_type, city, site, year_folder):
    """Создаёт структуру папок на удалённом хранилище"""
    # Заменяем None на значения по умолчанию
    operator = operator or 'Unknown'
    ne_type = ne_type or 'Unknown'
    city = city or 'Unknown'
    site = site or 'Unknown'
    year_folder = year_folder or 'permanent'
    
    remote_path = os.path.join(remote_base, operator, ne_type, city, site, year_folder)
    os.makedirs(remote_path, exist_ok=True)
    return remote_path

def move_to_old_folder(remote_file_path):
    """Перемещает старую версию файла в папку old/"""
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
    """Проверяет, нужно ли обновить файл на удалённом хранилище"""
    if not os.path.exists(remote_path):
        return True
    
    # Вычисляем хеш удалённого файла
    import hashlib
    hasher = hashlib.md5()
    with open(remote_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    remote_hash = hasher.hexdigest()
    
    return local_hash != remote_hash


def generate_license_filename(license_info):
    """
    Генерирует имя файла лицензии в формате:
    LIC{ne_type}{version_short}_{city}_{site}_{year}.dat
    Пример: LICCloudMRP6600_R23_MSK_IMS_8M_2027.dat
    """
    ne_type = license_info.get('ne_type', 'Unknown')
    version = license_info.get('version', '')
    city = license_info.get('city', 'Unknown')
    site = license_info.get('site', 'Unknown')
    
    # Сокращаем Version: V500R010 -> R10, V200R009 -> R9, 21 -> 21
    version_short = version
    if version:
        # Ищем R с цифрами
        r_match = re.search(r'R(\d+)', version, re.IGNORECASE)
        if r_match:
            version_short = 'R' + str(int(r_match.group(1)))  # Убираем ведущие нули
        else:
            # Если нет R, берём последние цифры
            digits = re.findall(r'\d+', version)
            if digits:
                version_short = digits[-1]
    
    # Определяем год по сроку действия
    valid_date = license_info.get('valid_date', '')
    year_folder = license_info.get('year', 'permanent')
    
    if valid_date and valid_date != 'PERMANENT' and valid_date != 'UNKNOWN':
        try:
            date_match = re.match(r'(\d{4})-(\d{2})', valid_date)
            if date_match:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                # Если месяц 1-3 -> предыдущий год, иначе текущий
                if month <= 3:
                    year_folder = str(year - 1)
                else:
                    year_folder = str(year)
        except:
            pass
    
    # Формируем имя файла
    filename = f"LIC{ne_type}_{version_short}_{city}_{site}_{year_folder}.dat"
    # Заменяем пробелы и спецсимволы на подчёркивания
    filename = re.sub(r'[^\w\-.]', '_', filename)
    
    return filename, year_folder

def sync_license_to_remote(license_info, remote_base, modified_by='system'):
    """Синхронизирует один файл лицензии на удалённое хранилище"""
    try:
        # Защита от None
        operator = license_info.get('operator') or 'Unknown'
        domain = license_info.get('domain') or 'Unknown'
        city = license_info.get('city') or 'Unknown'
        local_path = license_info.get('local_path') or ''
        file_hash = license_info.get('file_hash') or ''

        # Генерируем имя файла и год
        filename, year_folder = generate_license_filename(license_info)

        # Путь: {remote_base}/{operator}/{domain}/{city}/{year_folder}/
        remote_dir = os.path.join(remote_base, operator, domain, city, year_folder)
        os.makedirs(remote_dir, exist_ok=True)

        remote_file_path = os.path.join(remote_dir, filename)

        # Если local_path пустой — пропускаем копирование
        if not local_path or not os.path.exists(local_path):
            logger.warning(f"local_path пуст для {filename}, пропускаем копирование файла")
            save_license(license_info, modified_by)
            return True

        # Проверяем хеш
        if os.path.exists(remote_file_path) and file_hash:
            import hashlib
            hasher = hashlib.md5()
            with open(remote_file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            remote_hash = hasher.hexdigest()
            
            if remote_hash == file_hash:
                logger.debug(f"Файл не изменился: {filename}")
                save_license(license_info, modified_by)
                return True

        # Копируем файл
        if os.path.exists(local_path):
            if os.path.exists(remote_file_path):
                old_dir = os.path.join(remote_dir, 'old')
                os.makedirs(old_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                old_path = os.path.join(old_dir, f"{timestamp}_{filename}")
                shutil.move(remote_file_path, old_path)
                logger.info(f"Старая версия перемещена: {old_path}")

            shutil.copy2(local_path, remote_file_path)
            logger.info(f"Файл скопирован: {filename} -> {remote_file_path}")
        else:
            logger.warning(f"Локальный файл не найден: {local_path}")

        save_license(license_info, modified_by)
        return True

    except Exception as e:
        logger.error(f"Ошибка синхронизации {license_info.get('filename', 'unknown')}: {e}")
        return False

def sync_all_licenses(licenses, remote_base, modified_by='system'):
    """Синхронизирует все лицензии на удалённое хранилище"""
    success_count = 0
    fail_count = 0
    
    for license_info in licenses:
        if sync_license_to_remote(license_info, remote_base, modified_by):
            success_count += 1
        else:
            fail_count += 1
    
    logger.info(f"Синхронизация завершена: успешно {success_count}, ошибок {fail_count}")
    return success_count, fail_count

def download_db_from_remote(network_db_path, local_db_path):
    """Скачивает БД с удалённого хранилища"""
    if not os.path.exists(network_db_path):
        logger.warning(f"Удалённая БД не найдена: {network_db_path}")
        return False
    
    try:
        shutil.copy2(network_db_path, local_db_path)
        logger.info(f"БД скачана: {network_db_path} -> {local_db_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка скачивания БД: {e}")
        return False

def upload_db_to_remote(local_db_path, network_db_path):
    """Загружает БД на удалённое хранилище"""
    if not os.path.exists(local_db_path):
        logger.warning(f"Локальная БД не найдена: {local_db_path}")
        return False
    
    try:
        # Создаём папку назначения
        os.makedirs(os.path.dirname(network_db_path), exist_ok=True)
        shutil.copy2(local_db_path, network_db_path)
        logger.info(f"БД загружена: {local_db_path} -> {network_db_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка загрузки БД: {e}")
        return False