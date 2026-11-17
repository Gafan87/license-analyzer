# modules/license_service.py
"""
Сервисный слой для работы с лицензиями.
Инкапсулирует всю бизнес-логику и абстрагирует прямое обращение к БД.
"""

from modules.database import (
    get_connection, save_license, get_license_by_id, get_all_licenses,
    get_unique_esn_licenses, get_all_licenses_for_esn, get_filter_options
)
from modules.esn_mapper import get_mapping_by_esn, get_mapping_by_lsn
from modules.logger import get_logger
import time
import sqlite3
from modules.capacity_mapper import get_capacity_description

logger = get_logger(__name__)


class LicenseService:
    """Сервис для работы с лицензиями"""
    
    @staticmethod
    def get_licenses(operator=None, ne_type=None, city=None):
        """Получить список лицензий с фильтрацией"""
        return get_all_licenses(operator, ne_type, city)
    
    @staticmethod
    def get_unique_licenses_by_esn(operator):
        """Получить уникальные лицензии с группировкой по ESN"""
        return get_unique_esn_licenses(operator)
    
    @staticmethod
    def get_license_detail(license_id):
        """Получить полную информацию о лицензии по ID"""
        return get_license_by_id(license_id)
    
    @staticmethod
    def get_licenses_by_esn(operator, esn):
        """Получить все версии лицензии для конкретного ESN"""
        return get_all_licenses_for_esn(operator, esn)
    
    @staticmethod
    def save_license(license_data, modified_by='system'):
        """Сохранить или обновить лицензию"""
        return save_license(license_data, modified_by)
    
    @staticmethod
    def apply_mapping_batch(operator=None, force=False, max_retries=5):
        """
        Применить ESN маппинг ко всем лицензиям
        Args:
            operator: str - если указан, применяем только для этого оператора
            max_retries: int - количество попыток
        Returns:
            (updated, conflicts, errors)
        """
        conn = None
        for attempt in range(max_retries):
            try:
                conn = get_connection()
                cursor = conn.cursor()
                
                # Загружаем маппинг
                cursor.execute('SELECT esn, lsn, operator, domain, ne_type, city, site FROM esn_mapping')
                mapping_rows = cursor.fetchall()
                
                # Создаём словари для быстрого поиска
                mapping_by_esn = {}
                mapping_by_lsn = {}
                for esn, lsn, op, domain, ne, city, site in mapping_rows:
                    if esn:
                        mapping_by_esn[esn] = {
                            'operator': op, 'domain': domain, 'ne_type': ne, 
                            'city': city, 'site': site
                        }
                    if lsn:
                        mapping_by_lsn[lsn] = {
                            'operator': op, 'domain': domain, 'ne_type': ne, 
                            'city': city, 'site': site
                        }
                
                # Получаем лицензии (с фильтром по оператору если указан)
                if operator:
                    query = '''
                        SELECT id, esn, lsn, operator, domain, ne_type, city, site, year 
                        FROM licenses 
                        WHERE operator = ? AND ((esn IS NOT NULL AND esn != '') OR (lsn IS NOT NULL AND lsn != ''))
                    '''
                    cursor.execute(query, (operator,))
                else:
                    query = '''
                        SELECT id, esn, lsn, operator, domain, ne_type, city, site, year 
                        FROM licenses 
                        WHERE (esn IS NOT NULL AND esn != '') OR (lsn IS NOT NULL AND lsn != '')
                    '''
                    cursor.execute(query)
                
                licenses = cursor.fetchall()
                
                updated = 0
                conflicts = 0
                errors = 0
                
                for lic_id, esn, lsn, old_op, old_domain, old_ne, old_city, old_site, year in licenses:
                    try:
                        mapping = None
                        if esn and esn in mapping_by_esn:
                            mapping = mapping_by_esn[esn]
                        elif lsn and lsn in mapping_by_lsn:
                            mapping = mapping_by_lsn[lsn]
                        
                        if mapping:
                            new_op = mapping.get('operator') or old_op
                            new_domain = mapping.get('domain') or old_domain
                            new_ne = mapping.get('ne_type') or old_ne
                            new_city = mapping.get('city') or old_city
                            new_site = mapping.get('site') or old_site
                            
                            # Проверяем, изменились ли данные
                            if not force and (new_op == old_op and new_domain == old_domain and 
                                new_ne == old_ne and new_city == old_city and 
                                new_site == old_site):
                                continue
                            
                            # Проверяем конфликт заранее
                            cursor.execute('''
                                SELECT id FROM licenses 
                                WHERE operator = ? AND domain = ? AND ne_type = ? 
                                AND city = ? AND site = ? AND year = ? AND lsn = ?
                                AND id != ?
                            ''', (new_op, new_domain, new_ne, new_city, new_site, year, lsn, lic_id))
                            
                            if cursor.fetchone():
                                # Конфликт - удаляем текущую лицензию
                                cursor.execute('DELETE FROM resources WHERE license_id = ?', (lic_id,))
                                cursor.execute('DELETE FROM licenses WHERE id = ?', (lic_id,))
                                conflicts += 1
                            else:
                                # Обновляем
                                cursor.execute('''
                                    UPDATE licenses 
                                    SET operator = ?, domain = ?, ne_type = ?, city = ?, site = ?
                                    WHERE id = ?
                                ''', (new_op, new_domain, new_ne, new_city, new_site, lic_id))
                                updated += 1
                                
                    except sqlite3.IntegrityError as e:
                        # Неожиданный конфликт - логируем и пропускаем
                        logger.warning(f"IntegrityError при обработке лицензии {lic_id}: {e}")
                        conflicts += 1
                        continue
                    except Exception as e:
                        errors += 1
                        logger.error(f"Ошибка обработки лицензии {lic_id}: {e}")
                        continue
                
                conn.commit()
                conn.close()
                
                logger.info(f"Маппинг применён: обновлено {updated}, конфликтов {conflicts}, ошибок {errors}")
                return updated, conflicts, errors
                
            except sqlite3.IntegrityError as e:
                if conn:
                    conn.rollback()
                    conn.close()
                
                error_msg = str(e).lower()
                
                if "unique constraint" in error_msg:
                    # Это конфликт данных - не повторяем, просто логируем
                    logger.warning(f"Конфликт уникальности для лицензии (будет пропущена): {e}")
                    # Возвращаем нули, но не как ошибку
                    return 0, 0, 0
                elif attempt < max_retries - 1:
                    # Другие ошибки IntegrityError могут быть временными
                    logger.warning(f"IntegrityError, повторная попытка {attempt + 1}/{max_retries}")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    logger.error(f"Ошибка целостности БД после {max_retries} попыток: {e}")
                    return 0, 0, 0
                
            except Exception as e:
                if conn:
                    conn.rollback()
                    conn.close()
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.5 * (attempt + 1)
                    logger.warning(f"БД заблокирована, повторная попытка {attempt + 1}/{max_retries}")
                    time.sleep(wait_time)
                    continue
                raise e
        
        return 0, 0, 0

    @staticmethod
    def get_filter_options_for_operator(operator):
        """Получить варианты фильтров для оператора"""
        return get_filter_options(operator)
    
    @staticmethod
    def enrich_resources_with_descriptions(license_data, domain, network_storage_path):
        """
        Добавляет описания к ресурсам лицензии из capacity_mapper
        
        Args:
            license_data: dict - данные лицензии
            domain: str - домен
            network_storage_path: str - путь к сетевому хранилищу
        
        Returns:
            dict - license_data с обогащёнными ресурсами
        """
        from modules.capacity_mapper import get_capacity_description
        
        if not license_data.get('resources'):
            return license_data
        
        enriched_resources = []
        for res in license_data.get('resources', []):
            capacity_key = res.get('name')
            if capacity_key:
                description_data = get_capacity_description(capacity_key, domain, network_storage_path)
                if description_data:
                    res['description'] = description_data.get('description', '')
                    res['unit'] = description_data.get('unit', '')
                else:
                    res['description'] = ''
                    res['unit'] = ''
            enriched_resources.append(res)
        
        license_data['resources'] = enriched_resources
        return license_data


@staticmethod
def get_license_with_descriptions(license_id, domain, network_storage_path):
    """
    Получает лицензию по ID с обогащёнными описаниями ресурсов
    """
    license_data = get_license_by_id(license_id)
    if license_data:
        license_data = LicenseService.enrich_resources_with_descriptions(
            license_data, domain, network_storage_path
        )
    return license_data

class MappingService:
    """Сервис для работы с ESN маппингом"""
    
    @staticmethod
    def get_all_mappings():
        """Получить все записи маппинга"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT esn, lsn, operator, ne_type, city, site FROM esn_mapping')
        rows = cursor.fetchall()
        conn.close()
        return [{'esn': r[0], 'lsn': r[1], 'operator': r[2], 'ne_type': r[3], 'city': r[4], 'site': r[5]} for r in rows]
    
    @staticmethod
    def save_mappings(mappings, modified_by='system'):
        """Сохранить маппинг (с очисткой старых)"""
        from modules.esn_mapper import save_esn_mapping_to_db
        return save_esn_mapping_to_db(mappings, modified_by)
    
    @staticmethod
    def get_mapping_by_esn(esn):
        """Получить маппинг по ESN"""
        return get_mapping_by_esn(esn)
    
    @staticmethod
    def get_capacity_description_with_cache(capacity_key, domain, network_storage_path):
        """Получить описание CapacityKey с кэшированием"""
        return get_capacity_description(capacity_key, domain, network_storage_path)


class TargetService:
    """Сервис для работы с целями"""
    
    @staticmethod
    def get_targets(operator, ne_type, city, site):
        """Получить цели для сайта"""
        from modules.target_manager import get_targets_for_site
        return get_targets_for_site(operator, ne_type, city, site)
    
    @staticmethod
    def save_target(operator, ne_type, city, site, capacity_key, target_value, updated_by):
        """Сохранить цель"""
        from modules.target_manager import save_target_for_site
        return save_target_for_site(operator, ne_type, city, site, capacity_key, target_value, updated_by)
    
    @staticmethod
    def compare_with_targets(operator, ne_type, city, site, year):
        """Сравнить фактические ресурсы с целями"""
        from modules.target_manager import compare_with_targets
        return compare_with_targets(operator, ne_type, city, site, year)

class SyncService:
    """Сервис для синхронизации"""
    
    @staticmethod
    def sync_licenses(licenses, remote_base, modified_by='system'):
        """Синхронизировать лицензии на сервер"""
        from modules.sync_manager import sync_all_licenses
        return sync_all_licenses(licenses, remote_base, modified_by)
    
    @staticmethod
    def download_db(remote_path, local_path):
        """Скачать БД с сервера"""
        from modules.sync_manager import download_db_from_remote
        return download_db_from_remote(remote_path, local_path)
    
    @staticmethod
    def upload_db(local_path, remote_path):
        """Загрузить БД на сервер"""
        from modules.sync_manager import upload_db_to_remote
        return upload_db_to_remote(local_path, remote_path)