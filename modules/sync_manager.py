import os
import shutil
from datetime import datetime
from modules.logger import get_logger
from modules.database import save_license, get_connection

logger = get_logger(__name__)

def ensure_remote_path(remote_base, operator, ne_type, city, site, year_folder):
    """Создаёт структуру папок на удалённом хранилище"""
    # Путь: {remote_base}/{operator}/{ne_type}/{city}/{site}/{year_folder}/
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

def sync_license_to_remote(license_info, remote_base, modified_by='system'):
    """Синхронизирует один файл лицензии на удалённое хранилище"""
    try:
        # Определяем целевую папку
        year_folder = license_info.get('year') if license_info.get('year') else 'permanent'
        
        remote_dir = ensure_remote_path(
            remote_base,
            license_info['operator'],
            license_info['ne_type'],
            license_info['city'],
            license_info['site'],
            year_folder
        )
        
        remote_file_path = os.path.join(remote_dir, license_info['filename'])
        local_file_path = license_info['local_path']
        
        # Проверяем, нужно ли обновить
        if file_needs_update(license_info['file_hash'], remote_file_path):
            # Если файл существует, перемещаем старую версию в old/
            if os.path.exists(remote_file_path):
                move_to_old_folder(remote_file_path)
            
            # Копируем новый файл
            shutil.copy2(local_file_path, remote_file_path)
            logger.info(f"Файл скопирован: {remote_file_path}")
        
        # Сохраняем информацию в БД
        save_license(license_info, modified_by)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка синхронизации {license_info.get('filename')}: {e}")
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