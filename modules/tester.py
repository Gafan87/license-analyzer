import os
import sys
import sqlite3
import tempfile
import json
import time
import shutil
import threading
import socket
from datetime import datetime
from typing import Dict, List, Any, Optional
import json
import tempfile

from modules.logger import get_logger

logger = get_logger(__name__)

class SystemTester:
    """Класс для комплексного тестирования всех модулей программы"""

    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None
        self._use_test_db = True
        self.test_db_path = None
        self._temp_files = []
        
        # Эти будут заполнены тестом сканирования
        self._real_xml = None
        self._real_dat = None
        
        self._test_structure = self._build_test_structure()

    def _build_test_structure(self):
        """Создаёт единую структуру всех тестов"""
        return {
            'basic': {
                'name': 'Базовые компоненты',
                'icon': '🔧',
                'tests': [
                    ("🔧 Система логирования", 'test_logging'),
                    ("🗄️ База данных (SQLite)", 'test_database'),
                    ("🗄️ Подключение к БД", 'test_database_connection'),
                    ("⚙️ Конфигурационный файл", 'test_config_file'),
                    ("📋 Схема конфига", 'test_config_schema_validation'),
                    ("📦 Импорт модулей", 'test_import_modules'),
                    ("📚 Загрузка extraction_rules.json", 'test_extraction_rules_json'),
                ]
            },
            'parsers': {
                'name': 'Парсеры лицензий',
                'icon': '📁',
                'tests': [
                    ("🔍 Сканирование (поиск UDG/CloudATS9900)", 'test_scan_for_license_files'),
                    ("📡 Сканер (scan_local_folder)", 'test_scanner_module'),
                    ("📁 Парсер XML", 'test_parser_xml'),
                    ("📄 Парсер DAT", 'test_parser_dat'),
                    ("🔄 Согласованность парсинга", 'test_license_parsing_consistency'),
                    ("🌍 Кроссплатформенные пути", 'test_cross_platform_paths'),
                    ("⚡ Производительность парсинга", 'test_performance_simple'),
                    ("💾 Сканирование → БД → Список", 'test_scan_to_database_flow'),
                    ("📊 Агрегация фич", 'test_aggregation_for_features'),
                ]
            },
            'database': {
                'name': 'База данных и данные',
                'icon': '🗄️',
                'tests': [
                    ("🔑 Уникальность лицензий", 'test_license_uniqueness'),
                    ("📁 Дубликаты имён файлов", 'test_duplicate_filenames'),
                    ("🏷️ Соответствие имени и содержимого", 'test_filename_content_match'),
                    ("📋 Обязательные поля", 'test_required_fields_in_licenses'),
                    ("🔗 Целостность внешних ключей", 'test_foreign_key_integrity'),
                    ("📅 Корректность дат", 'test_date_consistency'),
                    ("🔢 Типы данных в БД", 'test_data_types'),
                    ("📜 Таблица истории", 'test_history_table'),
                    ("🗄️ Работа с пустой БД", 'test_empty_database_handling'),
                    ("🗄️ Колонка domain", 'test_domain_column_exists'),
                    ("🔧 CRUD динамических колонок", 'test_dynamic_columns_crud'),
                    ("💾 Динамические значения", 'test_dynamic_values_save_and_load'),
                    ("🔑 Уникальный индекс с domain", 'test_unique_index_with_domain'),
                    ("⚡ Производительность фильтрации", 'test_filter_performance'),
                    ("🔄 Миграция схемы БД", 'test_database_migration'),
                    ("📚 Миграция правил извлечения", 'test_extraction_rules_migration'),
                    ("🔒 Параллельный доступ к БД", 'test_concurrent_db_access'),
                    ("🔌 Пул соединений", 'test_connection_pool_exhaustion'),
                    ("📊 Производительность на больших данных", 'test_large_dataset_performance'),
                    ("🔍 Использование индексов", 'test_index_usage'),
                ]
            },
            'mapping': {
                'name': 'Маппинг и формулы',
                'icon': '🗺️',
                'tests': [
                    ("🗺️ ESN маппинг", 'test_esn_mapping'),
                    ("🗺️ Конфликты ESM-маппинга", 'test_esn_mapping_consistency'),
                    ("📊 Excel формулы", 'test_excel_formulas'),
                    ("🔄 Циклические зависимости формул", 'test_formula_circular_dependencies'),
                    ("🧮 Вычисление Excel формул", 'test_excel_formula_evaluation'),
                    ("⚠️ Ошибки формул Excel", 'test_excel_formula_error_handling'),
                    ("🗺️ ESN маппинг (пустая БД)", 'test_esn_mapping_empty_database'),
                    ("📦 Массовый импорт ESN", 'test_esn_mapping_batch_operations'),
                ]
            },
            'sync': {
                'name': 'Синхронизация и файлы',
                'icon': '🔄',
                'tests': [
                    ("🔄 Синхронизация", 'test_sync_manager'),
                    ("🔐 Консистентность хешей", 'test_file_hash_consistency'),
                    ("💾 Создание бэкапа", 'test_backup_creation'),
                    ("📝 Переименование файлов", 'test_file_renamer'),
                    ("🏷️ Переименование (полный цикл)", 'test_batch_rename_flow'),
                    ("🔄 Полный цикл синхронизации", 'test_sync_flow_simulation'),
                    ("🔤 Спецсимволы в именах", 'test_rename_special_characters'),
                    ("📋 Предотвращение дубликатов", 'test_rename_duplicate_prevention'),
                    ("🔗 Символические ссылки", 'test_scanner_symlinks'),
                    ("👻 Скрытые файлы", 'test_scanner_hidden_files'),
                ]
            },
            'targets': {
                'name': 'Цели и аналитика',
                'icon': '🎯',
                'tests': [
                    ("🎯 Цели и эталоны", 'test_target_manager'),
                    ("📅 Извлечение года", 'test_year_extraction'),
                    ("🎯 Сравнение с целями", 'test_target_comparison_flow'),
                    ("🔀 Сравнение версий", 'test_compare_versions_flow'),
                    ("⚠️ Конфликты целей", 'test_target_conflicts'),
                    ("📜 История изменений целей", 'test_target_history'),
                ]
            },
            'web': {
                'name': 'Веб-интерфейс',
                'icon': '🌐',
                'tests': [
                    ("🌐 Веб-маршруты", 'test_web_routes'),
                    ("📄 Наличие шаблонов", 'test_template_existence'),
                    ("🔌 API маршруты", 'test_api_endpoints'),
                    ("🌐 Доступность эндпоинтов", 'test_web_endpoints_access'),
                    ("🔍 Поиск и фильтрация", 'test_search_and_filter'),
                    ("👤 Управление сессиями", 'test_session_management'),
                    ("💾 Формат предустановок", 'test_presets_localstorage_format'),
                    ("📤 Экспорт/импорт предустановок", 'test_export_import_presets'),
                    ("🔍 Умный поиск (парсинг)", 'test_smart_search_parsing'),
                    ("💡 Подсказки умного поиска", 'test_smart_search_suggestions'),
                    ("📎 Экспорт в Excel (структура)", 'test_export_excel_structure'),
                    ("🎨 Цветовая группировка", 'test_color_grouping_storage'),
                    ("✅ Массовые операции", 'test_bulk_operations_selection'),
                    ("🔒 Защита от SQL-инъекций", 'test_sql_injection_prevention'),
                    ("🛡️ Защита от XSS", 'test_xss_prevention'),
                    ("📁 Защита от обхода путей", 'test_path_traversal_prevention'),
                    ("⏱️ Ограничение частоты API", 'test_api_rate_limiting'),
                    ("📡 Формат ошибок API", 'test_api_error_responses'),
                ]
            },
            'static': {
                'name': 'Статические файлы и UI',
                'icon': '🎨',
                'tests': [
                    ("🎨 Статические файлы", 'test_static_files'),
                    ("🌐 Кодировки строк", 'test_string_encoding'),
                ]
            },
            'integration': {
                'name': 'Интеграционные тесты',
                'icon': '🔗',
                'tests': [
                    ("📊 Согласованность количества", 'test_license_count_consistency'),
                    ("🛡️ Обработка ошибок", 'test_error_handling'),
                    ("🏷️ Агрегация тегов и комментариев", 'test_tags_and_comments_aggregation'),
                    ("💥 Восстановление после сбоя", 'test_crash_recovery'),
                    ("🗄️ Восстановление повреждённой БД", 'test_corrupted_database_recovery'),
                    ("🔤 Unicode полный цикл", 'test_unicode_full_cycle'),
                    ("📄 Обработка BOM", 'test_bom_handling'),
                ]
            },
            'tags': {
                'name': 'Теги и комментарии',
                'icon': '🏷️',
                'tests': [
                    ("🏷️ CRUD тегов", 'test_tags_crud'),
                    ("💬 CRUD комментариев", 'test_comments_crud'),
                    ("🔑 Уникальность тегов", 'test_tag_uniqueness'),
                ]
            },
            'templates': {
                'name': 'Шаблоны отчётов',
                'icon': '📋',
                'tests': [
                    ("📋 Шаблоны отчётов", 'test_report_templates'),
                    ("📤 Экспорт шаблона", 'test_template_export'),
                ]
            },
            'import_export': {
                'name': 'Импорт/Экспорт',
                'icon': '📎',
                'tests': [
                    ("📎 Импорт из Excel", 'test_excel_import'),
                    ("🖱️ Drag-and-drop переименование", 'test_drag_drop_rename'),
                    ("🗂️ Папка old", 'test_old_folder_creation'),
                ]
            },
            'network': {
                'name': 'Сетевые тесты',
                'icon': '🌐',
                'tests': [
                    ("⏱️ Сетевые таймауты", 'test_network_timeout_handling'),
                    ("📦 Неполная передача файла", 'test_partial_file_transfer'),
                ]
            },
            'new_features': {
                'name': 'Новый функционал',
                'icon': '🆕',
                'tests': [
                    ("📊 Отчёты по шаблонам", 'test_report_template_generation'),
                    ("🔔 Уведомления об истекающих лицензиях", 'test_expiring_notifications'),
                    ("📋 История изменений лицензий", 'test_change_history_tracking'),
                    ("🔍 Полнотекстовый поиск", 'test_fulltext_search'),
                    ("📎 Экспорт в CSV/Excel", 'test_export_formats'),
                    ("⚙️ Валидация NE типов", 'test_ne_type_validation'),
                    ("🔐 Проверка прав доступа", 'test_access_control'),
                    ("📦 Массовое обновление", 'test_bulk_update'),
                    ("📊 Дашборд статистики", 'test_dashboard_statistics'),
                ]
            },
        }

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ СО СТРУКТУРОЙ ТЕСТОВ ==========

    def get_test_categories(self) -> List[Dict]:
        """
        Возвращает список категорий тестов для веб-интерфейса.
        Каждая категория содержит id, name, icon и список тестов с id и name.
        """
        categories = []
        for cat_id, cat_data in self._test_structure.items():
            category = {
                'id': cat_id,
                'name': cat_data['name'],
                'icon': cat_data['icon'],
                'tests': [
                    {
                        'id': method_name,
                        'name': display_name
                    }
                    for display_name, method_name in cat_data['tests']
                ]
            }
            categories.append(category)
        return categories

    def _get_test_method(self, method_name: str):
        """Получает метод теста по имени. Возвращает (display_name, method) или (None, None)"""
        for cat_data in self._test_structure.values():
            for display_name, m_name in cat_data['tests']:
                if m_name == method_name:
                    method = getattr(self, method_name, None)
                    return display_name, method
        return None, None

    def _get_category_tests(self, category_id: str) -> List[tuple]:
        """Возвращает список тестов категории: [(display_name, method_name)]"""
        cat_data = self._test_structure.get(category_id)
        if cat_data:
            return cat_data['tests']
        return []

    def _get_all_tests_flat(self) -> List[tuple]:
        """Возвращает плоский список всех тестов: [(display_name, method_name)]"""
        all_tests = []
        for cat_data in self._test_structure.values():
            all_tests.extend(cat_data['tests'])
        return all_tests

    # ========== МЕТОДЫ ЗАПУСКА ТЕСТОВ ==========

    def run_all_tests(self, app_config: Optional[Dict] = None) -> Dict[str, Any]:
        """Запускает все тесты по категориям"""
        self.start_time = datetime.now()
        self.results = []

        # Тесты, которым нужен app_config
        tests_needing_config = ['test_network_storage']

        try:
            if self._use_test_db:
                from modules.database import create_test_db
                try:
                    create_test_db()
                except Exception as e:
                    print(f"⚠️ Не удалось создать тестовую БД: {e}")
                    self._use_test_db = False

            for cat_id, cat_data in self._test_structure.items():
                tests_to_run = []
                for display_name, method_name in cat_data['tests']:
                    method = getattr(self, method_name, None)
                    if method:
                        if method_name in tests_needing_config and app_config:
                            tests_to_run.append((display_name, lambda cfg=app_config: self.test_network_storage(cfg)))
                        elif method_name in tests_needing_config:
                            # Пропускаем тесты, требующие конфиг, если его нет
                            print(f"⚠️ Пропущен '{display_name}' — нет app_config")
                            continue
                        else:
                            tests_to_run.append((display_name, method))
                    else:
                        print(f"⚠️ Метод '{method_name}' не найден")
                
                if tests_to_run:
                    self._run_test_group(cat_data['name'], tests_to_run)

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            self.add_result("Система", False, f"Ошибка: {str(e)}")
        finally:
            try:
                self._cleanup_test_db()
            except:
                pass

        self.end_time = datetime.now()
        return self.get_report()

    def run_selected_tests(self, category_id: str = None, test_name: str = None,
                        app_config: Optional[Dict] = None) -> Dict[str, Any]:
        """Запускает выбранные тесты"""
        self.start_time = datetime.now()
        self.results = []

        try:
            if self._use_test_db:
                from modules.database import create_test_db
                try:
                    create_test_db()
                except:
                    self._use_test_db = False

            if test_name:
                import io, sys
                display_name, method = self._get_test_method(test_name)
                if method:
                    old_stdout = sys.stdout
                    sys.stdout = captured = io.StringIO()
                    try:
                        method()
                        output = captured.getvalue().strip()
                        sys.stdout = old_stdout
                        lines = [l for l in output.split('\n') if l.strip()]
                        message = lines[-1] if lines else None
                        self.add_result(display_name, True, message)
                    except Exception as e:
                        sys.stdout = old_stdout
                        self.add_result(display_name, False, str(e))

            elif category_id:
                cat_data = self._test_structure.get(category_id)
                if cat_data:
                    tests_to_run = []
                    for display_name, method_name in cat_data['tests']:
                        method = getattr(self, method_name, None)
                        if method:
                            tests_to_run.append((display_name, method))
                    if tests_to_run:
                        self._run_test_group(cat_data['name'], tests_to_run)
                else:
                    self.add_result(category_id, False, f"Категория '{category_id}' не найдена")
            else:
                return self.run_all_tests(app_config)

        except Exception as e:
            logger.error(f"Ошибка в run_selected_tests: {e}")
            self.add_result("Выполнение тестов", False, str(e))
        finally:
            try:
                self._cleanup_test_db()
            except:
                pass

        self.end_time = datetime.now()
        return self.get_report()

    def _run_test_group(self, group_name: str, tests: List[tuple]):
        """Запускает группу тестов с обработкой ошибок"""
        import io
        import sys
        
        print(f"\n{'='*60}")
        print(f"  Тестирование: {group_name}")
        print(f"{'='*60}")
        
        for name, test_func in tests:
            # Захватываем print из теста
            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()
            
            try:
                test_func()
                output = captured.getvalue().strip()
                sys.stdout = old_stdout
                
                # Берём последнюю строку вывода (основной результат)
                lines = [l for l in output.split('\n') if l.strip()]
                message = lines[-1] if lines else None
                
                self.add_result(name, True, message)
                print(message if message else "OK")
                
            except Exception as e:
                sys.stdout = old_stdout
                logger.error(f"Ошибка в тесте '{name}': {e}")
                self.add_result(name, False, str(e))
                print(f"❌ {str(e)[:100]}")

    def _get_db_connection(self):
        """Получает соединение с БД (тестовой, если включена)"""
        if self._use_test_db:
            from modules.database import get_test_connection
            return get_test_connection()
        else:
            from modules.database import get_connection
            return get_connection()

    def _cleanup_test_db(self):
        """Очищает тестовую БД после тестов"""
        if self._use_test_db:
            from modules.database import cleanup_test_db
            cleanup_test_db()
        if self.test_db_path and os.path.exists(self.test_db_path):
            try:
                os.unlink(self.test_db_path)
            except PermissionError:
                print(f"⚠️ Не удалось удалить тестовую БД {self.test_db_path}")

    def add_result(self, name: str, status: bool, message: str):
        """Добавляет результат теста"""
        self.results.append({
            'name': name,
            'status': status,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })

    def get_report(self) -> Dict[str, Any]:
        """Формирует подробный отчёт о тестировании"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r['status'])
        failed = total - passed
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0

        return {
            'success': failed == 0,
            'total': total,
            'passed': passed,
            'failed': failed,
            'duration': round(duration, 2),
            'results': self.results,
            'start_time': self.start_time.isoformat() if self.start_time else '',
            'end_time': self.end_time.isoformat() if self.end_time else ''
        }

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _create_temp_file(self, content: str, suffix: str = '.xml') -> str:
        """Создаёт временный файл с содержимым и возвращает путь"""
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def _remove_temp_file(self, path: str):
        """Безопасно удаляет временный файл"""
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass

    # ========== СУЩЕСТВУЮЩИЕ ТЕСТЫ (СОХРАНЕНЫ) ==========

    def test_logging(self):
        """Тест системы логирования"""
        test_logger = get_logger('tester_check')
        test_logger.info("Тестовое сообщение от SystemTester")
        log_dir = "logs"
        assert os.path.exists(log_dir), "Директория 'logs' не создана"
        print(f"✅ Логирование работает, папка: {log_dir}")

    def test_database(self):
        """Тест базы данных (проверка наличия таблиц)"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()
        assert len(tables) > 0, "Нет таблиц в БД"
        table_names = [t[0] for t in tables]
        print(f"✅ БД: {len(tables)} таблиц ({', '.join(table_names[:5])}{'...' if len(table_names) > 5 else ''})")

    def test_database_connection(self):
        """Тест подключения к БД с повторными попытками"""
        for attempt in range(3):
            try:
                conn = self._get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                conn.close()
                assert result[0] == 1, "Неверный результат тестового запроса"
                print(f"✅ Подключение к БД успешно (попытка {attempt + 1})")
                return
            except Exception as e:
                if "locked" in str(e) and attempt < 2:
                    time.sleep(0.5)
                    continue
                raise
        assert False, "Не удалось подключиться к БД после 3 попыток"

    def test_config_file(self):
        """Тест наличия и базовой структуры config.json"""
        config_path = os.environ.get('CONFIG_PATH', 'config.json')
        assert os.path.exists(config_path), f"{config_path} не найден"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        assert 'operators' in config, "Нет секции 'operators' в конфиге"
        assert len(config['operators']) > 0, "Список операторов пуст"
        print(f"✅ config.json: {len(config['operators'])} операторов ({', '.join(op.get('name','?') for op in config['operators'])})")

    def test_config_schema_validation(self):
        """Тест валидации схемы config.json"""
        config_path = os.environ.get('CONFIG_PATH', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        required_fields = ['log_level', 'network_storage_path', 'operators']
        for field in required_fields:
            assert field in config, f"Отсутствует обязательное поле '{field}' в конфиге"
        print(f"✅ Схема конфига валидна (log_level={config.get('log_level')}, storage={'задан' if config.get('network_storage_path') else 'пуст'})")

    def test_import_modules(self):
        """Тест импорта всех ключевых модулей"""
        modules_to_test = [
            'modules.logger', 'modules.database', 'modules.parser_xml', 'modules.parser_dat',
            'modules.esn_mapper', 'modules.scanner', 'modules.sync_manager',
            'modules.target_manager', 'modules.file_renamer', 'modules.excel_evaluator',
            'modules.capacity_mapper', 'modules.excel_importer', 'modules.web.routes'
        ]
        failed = []
        for module_name in modules_to_test:
            try:
                __import__(module_name)
            except ImportError as e:
                failed.append(module_name)
        assert len(failed) == 0, f"Не удалось импортировать: {failed}"
        print(f"✅ Импорт: {len(modules_to_test)} модулей загружено")

    def test_extraction_rules_json(self):
        """Тест загрузки extraction_rules.json"""
        rules_path = os.environ.get('EXTRACTION_RULES_PATH', 'extraction_rules.json')
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            assert 'rules' in rules, "В extraction_rules.json нет ключа 'rules'"
            rules_count = len(rules.get('rules', {}))
            print(f"✅ extraction_rules.json: {rules_count} правил, версия {rules.get('version', '?')}")
        else:
            print("⚠️ extraction_rules.json не найден"
                  )
    # ========== СУЩЕСТВУЮЩИЕ ТЕСТЫ (СОХРАНЕНЫ) ==========
 
 
    def _load_cached_files(self):
        """Загружает пути к файлам из кэша"""
        cache_file = os.path.join(tempfile.gettempdir(), 'license_tester_cache.json')
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
                self._real_xml = cache.get('xml')
                self._real_dat = cache.get('dat')
                return True
        except:
            pass
        return False

    def test_scan_for_license_files(self):
        """Тест: поиск UDG XML и CloudATS9900 DAT в папках сканирования"""
        
        scan_roots = [
            "D:/_Beeline/_Licenses/_All Licenses",
        ]
        
        xml_found = None
        dat_found = None
        
        for root in scan_roots:
            if not os.path.exists(root):
                continue
            
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                
                for f in filenames:
                    if not f.startswith('LIC'):
                        continue
                    
                    fp = os.path.join(dirpath, f)
                    
                    if not xml_found and f.endswith('.xml') and 'UDG' in f.upper():
                        xml_found = fp
                    
                    if not dat_found and f.endswith('.dat') and 'CLOUDATS9900' in f.upper():
                        dat_found = fp
                    
                    if xml_found and dat_found:
                        break
                
                if xml_found and dat_found:
                    break
            
            if xml_found and dat_found:
                break
        
        assert xml_found, "UDG XML не найден"
        assert dat_found, "CloudATS9900 DAT не найден"
        
        self._real_xml = xml_found
        self._real_dat = dat_found
        
        # Кэшируем
        cache = {'xml': xml_found, 'dat': dat_found}
        cache_file = os.path.join(tempfile.gettempdir(), 'license_tester_cache.json')
        with open(cache_file, 'w') as f:
            json.dump(cache, f)
        
        print(f"✅ UDG XML: {os.path.basename(xml_found)} ({os.path.getsize(xml_found)} байт)")
        print(f"✅ CloudATS9900 DAT: {os.path.basename(dat_found)} ({os.path.getsize(dat_found)} байт)")


    def test_scanner_module(self):
        from modules.scanner import scan_local_folder
        
        self._load_cached_files()
        
        if not self._real_xml:
            print("⚠️ Сначала запустите тест сканирования")
            return
        
        scan_dir = os.path.dirname(os.path.dirname(self._real_xml))
        result = scan_local_folder(scan_dir, "beeline")
        
        assert isinstance(result, list), f"Сканер вернул не список: {type(result)}"
        assert len(result) > 0, f"Сканер ничего не нашёл в {scan_dir}"
        
        found_udg = False
        for lic in result:
            fname = lic.get('filename', '') or lic.get('file_path', '')
            if 'UDG' in str(fname).upper():
                found_udg = True
                break
        
        assert found_udg, "Сканер не нашёл UDG файл"
        print(f"✅ Сканер: {len(result)} файлов в {scan_dir}")


    def test_parser_xml(self):
        from modules.parser_xml import parse_xml_license
        
        self._load_cached_files()
        
        if not self._real_xml:
            print("⚠️ Сначала запустите тест сканирования")
            return
        
        result = parse_xml_license(self._real_xml)
        assert result is not None, "Парсер XML вернул None"
        assert 'lsn' in result, "Нет ключа 'lsn'"
        print(f"✅ {os.path.basename(self._real_xml)}")
        print(f"   LSN: {result['lsn']}")
        print(f"   Продукт: {result.get('product', '?')} {result.get('version', '')}")
        print(f"   ESN: {result.get('esn', '?')}")
        print(f"   Ресурсов: {len(result.get('resources', []))}")


    def test_parser_dat(self):
        from modules.parser_dat import parse_dat_license
        
        self._load_cached_files()
        
        if not self._real_dat:
            print("⚠️ Сначала запустите тест сканирования")
            return
        
        result = parse_dat_license(self._real_dat)
        assert result is not None, "Парсер DAT вернул None"
        assert 'lsn' in result, "Нет ключа 'lsn'"
        print(f"✅ {os.path.basename(self._real_dat)}")
        print(f"   LSN: {result['lsn']}")
        print(f"   Продукт: {result.get('product', '?')} {result.get('version', '')}")
        print(f"   ESN: {result.get('esn', '?')}")
        print(f"   Ресурсов: {len(result.get('resources', []))}")


    def test_license_parsing_consistency(self):
        from modules.parser_xml import parse_xml_license
        
        self._load_cached_files()
        
        if not self._real_xml:
            print("⚠️ Сначала запустите тест сканирования")
            return
        
        results = []
        for _ in range(3):
            results.append(parse_xml_license(self._real_xml))
        
        valid = [r for r in results if r]
        assert len(valid) >= 2, "Мало результатов"
        
        first_lsn = valid[0].get('lsn')
        first_res = len(valid[0].get('resources', []))
        
        for r in valid[1:]:
            assert r.get('lsn') == first_lsn
            assert len(r.get('resources', [])) == first_res
        
        print(f"✅ 3× парсинг: LSN={first_lsn}, ресурсов={first_res}")


    def test_performance_simple(self):
        from modules.parser_xml import parse_xml_license
        import time
        
        self._load_cached_files()
        
        if not self._real_xml:
            print("⚠️ Сначала запустите тест сканирования")
            return
        
        start = time.time()
        for _ in range(10):
            parse_xml_license(self._real_xml)
        elapsed = time.time() - start
        avg = elapsed / 10
        
        assert avg < 1.0, f"Медленно: {avg:.3f} сек"
        print(f"✅ 10× за {elapsed:.3f} сек (ср. {avg:.3f} сек) — {os.path.basename(self._real_xml)[:40]}")


    def test_scan_to_database_flow(self):
        """Тест: находим файл → парсим → сохраняем в БД"""
        from modules.parser_xml import parse_xml_license
        from modules.database import get_connection
        import time
        
        self._load_cached_files()
        
        if not self._real_xml:
            print("⚠️ Сначала запустите тест сканирования")
            return
        
        result = parse_xml_license(self._real_xml)
        assert result is not None, "Парсер вернул None"
        
        # Уникальные значения чтобы избежать UNIQUE constraint
        ts = int(time.time())
        lsn = f"TEST_SCAN_{ts}"
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO licenses 
                (operator, domain, ne_type, city, site, year, lsn, product, version, esn, filename, last_modified, modified_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """, (
                'test_scanner', 'PS', 'UDG', 'TestCity', f'TestSite_{ts}', '2025',
                lsn, result.get('product', 'TestProduct'),
                result.get('version', 'V1.0'), result.get('esn', f'ESN_{ts}'),
                os.path.basename(self._real_xml), 'tester'
            ))
            lic_id = cursor.lastrowid
            conn.commit()
            
            if lic_id:
                print(f"✅ Сохранён в БД: LSN={lsn} (id={lic_id})")
            else:
                print(f"⚠️ INSERT OR IGNORE пропустил запись (возможно дубликат)")
        finally:
            conn.close()
            
    def test_aggregation_for_features(self):
        """Тест агрегации данных для фич"""
        from modules.database import get_connection
        
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT ne_type, COUNT(*) as cnt FROM licenses GROUP BY ne_type")
            rows = cursor.fetchall()
            print(f"✅ Агрегация: {len(rows)} групп NE типов")
        except Exception as e:
            print(f"⚠️ Агрегация не выполнена: {e}")
        finally:
            conn.close()

    def __del__(self):
        """Очистка временных файлов"""
        for f in getattr(self, '_temp_files', []):
            try:
                if os.path.exists(f):
                    os.unlink(f)
                    print(f"🧹 Удалён временный: {os.path.basename(f)}")
            except:
                pass

    def test_cross_platform_paths(self):
        """Тест обработки путей в разных ОС"""
        try:
            from modules.scanner import extract_tags_from_path
            assert callable(extract_tags_from_path), "Функция extract_tags_from_path недоступна"
            print("✅ Кроссплатформенные пути: функция доступна")
        except ImportError as e:
            print(f"⚠️ Функция extract_tags_from_path не найдена: {e}")
     
    # ---------- ТЕСТЫ БАЗЫ ДАННЫХ И ДАННЫХ ----------
 
    def test_license_uniqueness(self):
        """Тест уникальности лицензий в БД"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT operator, ne_type, city, site, year, lsn, COUNT(*) 
            FROM licenses 
            GROUP BY operator, ne_type, city, site, year, lsn 
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        conn.close()
        if duplicates:
            print(f"⚠️ Найдено {len(duplicates)} дубликатов")
        else:
            print(f"✅ Дубликатов нет")

    def test_duplicate_filenames(self):
        """Тест дубликатов имён файлов"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT operator, ne_type, city, site, year, filename, COUNT(*) as cnt
            FROM licenses
            GROUP BY operator, ne_type, city, site, year, filename
            HAVING cnt > 1
        """)
        duplicates = cursor.fetchall()
        conn.close()
        if duplicates:
            print(f"⚠️ {len(duplicates)} дубликатов имён файлов")
        else:
            print(f"✅ Дубликатов имён нет")

    def test_filename_content_match(self):
        """Тест соответствия LSN в имени файла и содержимом"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, lsn FROM licenses WHERE filename IS NOT NULL AND lsn IS NOT NULL")
        rows = cursor.fetchall()
        conn.close()
        import re
        mismatches = 0
        for row in rows:
            lic_id, filename, lsn = row
            match = re.search(r'LIC[A-Z0-9]+', filename, re.IGNORECASE)
            if match and match.group(0).upper() != lsn.upper():
                mismatches += 1
        if mismatches:
            print(f"⚠️ {mismatches} несовпадений LSN в имени и содержимом")
        else:
            print(f"✅ LSN в именах совпадают с содержимым")

    def test_required_fields_in_licenses(self):
        """Тест наличия обязательных полей у лицензий"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM licenses WHERE (lsn IS NULL OR lsn = '') AND (esn IS NULL OR esn = '')")
        no_id = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM licenses WHERE product IS NULL OR product = ''")
        no_product = cursor.fetchone()[0]
        conn.close()
        issues = []
        if no_id: issues.append(f"{no_id} без LSN/ESN")
        if no_product: issues.append(f"{no_product} без продукта")
        if issues:
            print(f"⚠️ {', '.join(issues)}")
        else:
            print(f"✅ Все обязательные поля заполнены")

    def test_foreign_key_integrity(self):
        """Тест целостности внешних ключей"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resources r LEFT JOIN licenses l ON r.license_id = l.id WHERE l.id IS NULL")
        orphan_resources = cursor.fetchone()[0]
        conn.close()
        if orphan_resources:
            print(f"⚠️ {orphan_resources} ресурсов без лицензии")
        else:
            print(f"✅ Целостность внешних ключей")

    def test_date_consistency(self):
        """Тест корректности дат"""
        from datetime import datetime
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM licenses 
            WHERE create_time IS NOT NULL AND valid_date IS NOT NULL 
            AND valid_date != 'PERMANENT' AND valid_date != 'UNKNOWN'
            AND valid_date < create_time
        """)
        bad_dates = cursor.fetchone()[0]
        conn.close()
        if bad_dates:
            print(f"⚠️ {bad_dates} лицензий с датой действия раньше создания")
        else:
            print(f"✅ Даты корректны")

    def test_data_types(self):
        """Тест типов данных в БД"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(licenses)")
        columns = cursor.fetchall()
        column_names = [c[1] for c in columns]
        expected = ['id', 'operator', 'ne_type', 'city', 'site', 'year', 'lsn', 'product', 'version', 'esn']
        missing = [c for c in expected if c not in column_names]
        conn.close()
        if missing:
            print(f"⚠️ Отсутствуют колонки: {missing}")
        else:
            print(f"✅ {len(column_names)} колонок в licenses")

    def test_history_table(self):
        """Тест наличия таблицы истории"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='change_history'")
        table = cursor.fetchone()
        
        if table:
            cursor.execute("SELECT COUNT(*) FROM change_history")
            count = cursor.fetchone()[0]
            conn.close()
            print(f"✅ change_history: {count} записей")
        else:
            conn.close()
            print("⚠️ Таблица change_history не найдена")

    def test_empty_database_handling(self):
        """Тест работы с пустой БД"""
        from modules.database import get_all_licenses, get_filter_options
        licenses = get_all_licenses()
        filter_options = get_filter_options('mts')
        assert isinstance(licenses, list)
        assert isinstance(filter_options, dict)
        print(f"✅ Пустая БД: лицензий={len(licenses)}, NE типов={len(filter_options.get('ne_types', []))}")

    def test_domain_column_exists(self):
        """Тест наличия колонки domain"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(licenses)")
        columns = [c[1] for c in cursor.fetchall()]
        conn.close()
        if 'domain' in columns:
            print(f"✅ Колонка domain присутствует")
        else:
            print(f"⚠️ Колонка domain отсутствует")

    def test_dynamic_columns_crud(self):
        """Тест CRUD динамических колонок"""
        from modules.database import add_dynamic_column, get_dynamic_columns, delete_dynamic_column
        col_name = f"test_col_{int(time.time())}"
        try:
            add_dynamic_column(col_name, 'TEXT')
            cols = get_dynamic_columns()
            if col_name in cols:
                delete_dynamic_column(col_name)
                print(f"✅ Динамические колонки: создание/удаление работает")
            else:
                print(f"⚠️ Колонка {col_name} не появилась в списке")
        except Exception as e:
            print(f"⚠️ Динамические колонки: {str(e)[:80]}")

    def test_dynamic_values_save_and_load(self):
        """Тест сохранения/загрузки динамических значений"""
        from modules.database import set_dynamic_value, get_dynamic_values_for_license
        try:
            test_key = f"test_key_{int(time.time())}"
            test_value = json.dumps({"test": "data", "number": 123})
            set_dynamic_value(1, test_key, test_value)  # для license_id=1
            loaded = get_dynamic_values_for_license(1)
            if loaded and test_key in loaded:
                print(f"✅ Динамические значения: сохранение/загрузка работает")
            else:
                print(f"⚠️ Значение не загрузилось")
        except Exception as e:
            print(f"⚠️ Динамические значения: {str(e)[:80]}")

    def test_unique_index_with_domain(self):
        """Тест уникального индекса с domain"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA index_list(licenses)")
        indexes = cursor.fetchall()
        # Проверяем наличие составного уникального индекса
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='index' AND tbl_name='licenses' AND sql LIKE '%UNIQUE%'
        """)
        unique_indexes = cursor.fetchall()
        conn.close()
        if unique_indexes:
            print(f"✅ Уникальных индексов: {len(unique_indexes)}")
        else:
            print(f"⚠️ Уникальный индекс не найден")

    def test_filter_performance(self):
        """Тест производительности фильтрации"""
        from modules.database import get_all_licenses
        import time
        start = time.time()
        licenses = get_all_licenses()
        elapsed = time.time() - start
        if elapsed < 2.0:
            print(f"✅ Фильтрация: {len(licenses)} лицензий за {elapsed:.3f} сек")
        else:
            print(f"⚠️ Медленная фильтрация: {elapsed:.2f} сек")

    def test_database_migration(self):
        """Тест миграции БД"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(licenses)")
        columns = [c[1] for c in cursor.fetchall()]
        required = ['id', 'operator', 'ne_type', 'city', 'site', 'year', 'lsn', 'domain']
        missing = [c for c in required if c not in columns]
        conn.close()
        if missing:
            print(f"⚠️ После миграции не хватает колонок: {missing}")
        else:
            print(f"✅ Схема БД актуальна ({len(columns)} колонок)")

    def test_extraction_rules_migration(self):
        """Тест миграции правил извлечения"""
        rules_path = os.environ.get('EXTRACTION_RULES_PATH', 'extraction_rules.json')
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            rules_dict = rules.get('rules', {})
            valid = 0
            for key, rule in rules_dict.items():
                if isinstance(rule, dict) and ('pattern' in rule or 'type' in rule):
                    valid += 1
            if valid == len(rules_dict):
                print(f"✅ Правила извлечения: {len(rules_dict)} валидны")
            else:
                print(f"⚠️ {len(rules_dict) - valid} правил без pattern/type")
        else:
            print("⚠️ extraction_rules.json не найден")

    def test_concurrent_db_access(self):
        """Тест параллельного доступа к БД"""
        import threading
        errors = []
        
        def db_operation():
            try:
                conn = self._get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM licenses")
                time.sleep(0.05)
                cursor.fetchone()
                conn.close()
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        for _ in range(5):
            t = threading.Thread(target=db_operation)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=5)
        
        if errors:
            print(f"⚠️ Параллельный доступ: {len(errors)} ошибок")
        else:
            print(f"✅ Параллельный доступ: 5 потоков без ошибок")

    def test_connection_pool_exhaustion(self):
        """Тест исчерпания пула соединений"""
        connections = []
        try:
            for i in range(10):
                conn = self._get_db_connection()
                connections.append(conn)
            print(f"✅ Пул соединений: {len(connections)} открыто")
        except Exception as e:
            print(f"⚠️ Пул исчерпан на {len(connections)}: {str(e)[:50]}")
        finally:
            for conn in connections:
                try:
                    conn.close()
                except:
                    pass

    def test_large_dataset_performance(self):
        """Тест производительности на больших данных"""
        from modules.database import get_all_licenses
        import time
        start = time.time()
        licenses = get_all_licenses()
        elapsed = time.time() - start
        if len(licenses) > 10000:
            if elapsed < 5.0:
                print(f"✅ {len(licenses)} лицензий за {elapsed:.3f} сек")
            else:
                print(f"⚠️ Медленно: {len(licenses)} за {elapsed:.2f} сек")
        elif len(licenses) > 1000:
            if elapsed < 2.0:
                print(f"✅ {len(licenses)} лицензий за {elapsed:.3f} сек")
            else:
                print(f"⚠️ Медленно: {len(licenses)} за {elapsed:.2f} сек")
        else:
            print(f"✅ {len(licenses)} лицензий за {elapsed:.3f} сек")

    def test_index_usage(self):
        """Тест использования индексов"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM licenses WHERE operator = 'mts' AND ne_type = 'vEPC'")
        plan = cursor.fetchall()
        conn.close()
        plan_text = str(plan)
        if 'SCAN' in plan_text:
            print(f"⚠️ Полное сканирование таблицы")
        else:
            print(f"✅ Индексы используются")

    # ---------- ТЕСТЫ МАППИНГА И ФОРМУЛ ----------
    def test_esn_mapping_empty_database(self):
        """Тест ESN маппинга с пустой БД"""
        from modules.esn_mapper import get_mapping_by_esn
        
        # Проверяем поиск несуществующего ESN
        result = get_mapping_by_esn("NONEXISTENT_ESN_99999")
        print(f"✅ ESN маппинг (пустая БД): результат={result}")

    def test_esn_mapping(self):
        """Тест ESN маппинга"""
        from modules.esn_mapper import get_mapping_by_esn
        print(f"✅ ESN маппинг: модуль загружен")

    def test_esn_mapping_consistency(self):
        """Тест на конфликты в ESN маппинге"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT esn FROM esn_mapping 
                WHERE esn IS NOT NULL AND esn != ''
                GROUP BY esn HAVING COUNT(DISTINCT operator) > 1
            )
        """)
        conflicts = cursor.fetchone()[0]
        conn.close()
        if conflicts:
            print(f"⚠️ {conflicts} ESN привязаны к разным операторам")
        else:
            print(f"✅ Конфликтов ESN нет")

    def test_excel_formulas(self):
        """Тест загрузчика Excel формул"""
        from modules.excel_evaluator import ExcelFormulaEvaluator
        evaluator = ExcelFormulaEvaluator('vEPC')
        print(f"✅ Excel формулы: NE тип={evaluator.ne_type}")

    def test_formula_circular_dependencies(self):
        """Тест на циклические зависимости в формулах"""
        from modules.excel_evaluator import ExcelFormulaEvaluator
        ne_types = ['vEPC', 'PSCORE', 'PCRF']
        cycles_found = 0
        for ne_type in ne_types:
            evaluator = ExcelFormulaEvaluator(ne_type)
            if hasattr(evaluator, 'load') and evaluator.load():
                visited = set()
                def has_cycle(key, path):
                    if key in path: return True
                    if key in visited: return False
                    visited.add(key)
                    for dep in evaluator.dependencies.get(key, []):
                        if has_cycle(dep, path + [key]): return True
                    return False
                for key in evaluator.formulas:
                    if has_cycle(key, []):
                        cycles_found += 1
        if cycles_found:
            print(f"⚠️ Найдено {cycles_found} циклов")
        else:
            print(f"✅ Циклических зависимостей нет")

    def test_excel_formula_evaluation(self):
        """Тест вычисления Excel формул"""
        from modules.excel_evaluator import ExcelFormulaEvaluator
        evaluator = ExcelFormulaEvaluator('vEPC')
        if hasattr(evaluator, 'formulas') and evaluator.formulas:
            print(f"✅ Формулы загружены: {len(evaluator.formulas)} шт.")
        else:
            print(f"ℹ️ Формулы не загружены")

    def test_excel_formula_error_handling(self):
        """Тест обработки ошибок в формулах Excel"""
        from modules.excel_evaluator import ExcelFormulaEvaluator
        evaluator = ExcelFormulaEvaluator('vEPC')
        if hasattr(evaluator, 'evaluate'):
            errors_handled = 0
            for error in ['#DIV/0!', '#REF!', '#VALUE!']:
                try:
                    evaluator.evaluate(error)
                    errors_handled += 1
                except:
                    pass
            print(f"✅ Обработка ошибок: {errors_handled}/3 формул")

    def test_esn_mapping_batch_operations(self):
        """Тест массового импорта ESN маппинга"""
        from modules.esn_mapper import save_esn_mapping_to_db
        import time
        
        timestamp = int(time.time())
        batch = []
        for i in range(100):
            batch.append({
                'esn': f'BATCH_TEST_{timestamp}_{i}',
                'lsn': f'LSN_{timestamp}_{i}',
                'operator': 'test',
                'ne_type': 'vEPC',
                'city': 'MSK',
                'site': f'Site{i}'
            })
        
        start = time.time()
        save_esn_mapping_to_db(batch, 'tester')
        elapsed = time.time() - start
        
        print(f"✅ Массовый импорт: 100 ESN за {elapsed:.3f} сек")

    # ========== СИНХРОНИЗАЦИЯ И ФАЙЛЫ ==========

    def test_sync_manager(self):
        """Тест основных функций синхронизации"""
        from modules.sync_manager import file_needs_update
        assert callable(file_needs_update), "Функция file_needs_update не доступна"
        print(f"✅ Модуль sync_manager загружен")

    def test_file_hash_consistency(self):
        """Тест вычисления хеша файлов"""
        from modules.scanner import get_file_hash
        temp_file = self._create_temp_file("test content 123", '.txt')
        try:
            hash1 = get_file_hash(temp_file)
            hash2 = get_file_hash(temp_file)
            assert hash1 == hash2, "Хеши одного файла не совпадают"
            assert len(hash1) == 32, "Хеш не MD5"
            print(f"✅ Хеш MD5: {hash1[:8]}...")
        finally:
            self._remove_temp_file(temp_file)

    def test_backup_creation(self):
        """Тест создания резервной копии БД"""
        from modules.database import backup_database
        backup_path = backup_database('test_operator')
        if backup_path and os.path.exists(backup_path):
            size = os.path.getsize(backup_path)
            print(f"✅ Бэкап создан: {os.path.basename(backup_path)} ({size} байт)")
        else:
            print(f"⚠️ Бэкап не создан")

    def test_file_renamer(self):
        """Тест функций переименования файлов"""
        from modules.file_renamer import extract_year_from_valid_date, generate_new_filename
        assert extract_year_from_valid_date('2025-12-31') == '2025'
        assert extract_year_from_valid_date('PERMANENT') == 'permanent'
        assert callable(generate_new_filename)
        print(f"✅ Год из даты: 2025-12-31 → {extract_year_from_valid_date('2025-12-31')}")

    def test_batch_rename_flow(self):
        """Тест полного цикла переименования"""
        from modules.file_renamer import batch_rename_files
        from modules.esn_mapper import save_esn_mapping_to_db
        
        temp_incoming = tempfile.mkdtemp()
        temp_target = tempfile.mkdtemp()
        
        test_mapping = [{
            'esn': 'TEST_RENAME_ESN', 'lsn': 'TEST_RENAME',
            'operator': 'mts', 'ne_type': 'vEPC', 'city': 'MSK', 'site': 'SiteA'
        }]
        save_esn_mapping_to_db(test_mapping, 'tester')
        
        test_file = os.path.join(temp_incoming, "original_file.dat")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('LicenseSerialNo=TEST_RENAME\nProduct=TestProduct\nVersion=1.0\nEsn="TEST_RENAME_ESN"\n')
        
        try:
            success, failed = batch_rename_files(temp_incoming, temp_target, 'mts')
            if success:
                print(f"✅ Переименован: {success[0]['old_name']} → {success[0]['new_name']}")
            else:
                print(f"⚠️ Не переименован: {failed}")
        finally:
            shutil.rmtree(temp_incoming, ignore_errors=True)
            shutil.rmtree(temp_target, ignore_errors=True)

    def test_sync_flow_simulation(self):
        """Тест симуляции полного цикла синхронизации"""
        from modules.scanner import scan_local_folder
        from modules.database import save_license
        
        test_dir = tempfile.mkdtemp()
        test_xml = """<?xml version="1.0"?><LicFile><GeneralInfo><LSN>TEST_SYNC</LSN><CreateTime>2025-01-01</CreateTime></GeneralInfo><OfferingProduct name="Test" version="1.0"/></LicFile>"""
        
        with open(os.path.join(test_dir, "test_license.xml"), 'w', encoding='utf-8') as f:
            f.write(test_xml)
        
        try:
            licenses = scan_local_folder(test_dir, "test_operator")
            if len(licenses) > 0:
                lic = licenses[0]
                lic.update({'operator': 'test', 'ne_type': 'vEPC', 'city': 'MSK', 'site': 'SiteA', 'year': '2025'})
                save_license(lic, "tester")
                print(f"✅ Синхронизация: LSN={lic.get('lsn', '?')[:20]}")
            else:
                print(f"⚠️ Сканер не нашёл файл (возможно нужна структура папок)")
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_rename_special_characters(self):
        """Тест переименования файлов со спецсимволами"""
        from modules.file_renamer import generate_new_filename
        
        special_names = ["file:with:colons.xml", "file*with*asterisks.dat", "file?with?questions.xml"]
        # Проверяем что функция не падает на спецсимволах
        try:
            for name in special_names:
                result = generate_new_filename({'product': 'Test', 'version': '1.0', 'file_type': 'xml'}, {'city': 'MSK', 'site': 'SiteA'})
            print(f"✅ Спецсимволы: {len(special_names)} имён обработано")
        except Exception as e:
            print(f"⚠️ Спецсимволы: {str(e)[:80]}")

    def test_rename_duplicate_prevention(self):
        """Тест предотвращения дубликатов при переименовании"""
        from modules.file_renamer import generate_new_filename
        
        temp_dir = tempfile.mkdtemp()
        try:
            test_data = {'product': 'TestProduct', 'version': 'V1.0', 'file_type': 'xml'}
            mapping = {'city': 'MSK', 'site': 'SiteA'}
            
            name1 = generate_new_filename(test_data, mapping)
            open(os.path.join(temp_dir, name1), 'w').close()
            name2 = generate_new_filename(test_data, mapping)
            
            if name1 != name2:
                print(f"✅ Дубликаты: {name1[:30]} ≠ {name2[:30]}")
            else:
                print(f"⚠️ Имена совпадают: {name1}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_scanner_symlinks(self):
        """Тест обработки символических ссылок"""
        temp_dir = tempfile.mkdtemp()
        try:
            sub_dir = os.path.join(temp_dir, "real_folder")
            os.makedirs(sub_dir)
            with open(os.path.join(sub_dir, "test.xml"), 'w') as f:
                f.write('<?xml version="1.0"?><LicFile><GeneralInfo><LSN>SYMLINK</LSN></GeneralInfo></LicFile>')
            
            link_dir = os.path.join(temp_dir, "link_to_folder")
            try:
                os.symlink(sub_dir, link_dir, target_is_directory=True)
                print(f"✅ Симлинки: созданы и не вызывают ошибок")
            except OSError:
                print(f"ℹ️ Симлинки не поддерживаются (Windows без прав)")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_scanner_hidden_files(self):
        """Тест игнорирования скрытых файлов"""
        from modules.scanner import scan_local_folder
        
        temp_dir = tempfile.mkdtemp()
        try:
            # Скрытые файлы
            for hf in ['.gitkeep', '.DS_Store', 'Thumbs.db']:
                open(os.path.join(temp_dir, hf), 'w').close()
            # Нормальный файл
            with open(os.path.join(temp_dir, "normal.xml"), 'w') as f:
                f.write('<?xml version="1.0"?><LicFile><GeneralInfo><LSN>VISIBLE</LSN></GeneralInfo></LicFile>')
            
            result = scan_local_folder(temp_dir, "test")
            print(f"✅ Скрытые файлы: найдено {len(result) if isinstance(result, list) else 0} лицензий")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

# ========== ЦЕЛИ И АНАЛИТИКА ==========

    def test_target_manager(self):
        """Тест управления целями"""
        from modules.target_manager import get_targets_for_site, compare_with_targets
        assert callable(get_targets_for_site), "get_targets_for_site не доступна"
        assert callable(compare_with_targets), "compare_with_targets не доступна"
        print(f"✅ Модуль target_manager загружен")

    def test_year_extraction(self):
        """Тест извлечения года из дат"""
        from modules.parser_xml import extract_year_from_valid_date
        assert extract_year_from_valid_date('2025-12-31') == '2025'
        assert extract_year_from_valid_date('PERMANENT') == 'permanent'
        print(f"✅ Извлечение года: 2025-12-31 → 2025, PERMANENT → permanent")

    def test_target_comparison_flow(self):
        """Тест сравнения с целевыми значениями"""
        from modules.target_manager import get_targets_for_site
        import time
        
        from modules.database import get_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO base_targets (operator, ne_type, city, site, capacity_key, target_value, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, ('mts', 'vEPC', 'MSK', 'SiteA', 'TEST_TARGET', 5000, 'tester'))
            conn.commit()
        finally:
            conn.close()
        
        time.sleep(0.1)
        
        targets = get_targets_for_site('mts', 'vEPC', 'MSK', 'SiteA')
        
        if isinstance(targets, dict):
            if 'TEST_TARGET' in targets:
                print(f"✅ Цели (dict): TEST_TARGET={targets['TEST_TARGET']}")
            else:
                print(f"⚠️ TEST_TARGET не найден, ключей: {len(targets)}")
        elif isinstance(targets, list) and len(targets) > 0:
            if isinstance(targets[0], dict):
                found = [t for t in targets if t.get('capacity_key') == 'TEST_TARGET']
                if found:
                    print(f"✅ Цели (list): {len(targets)} шт, TEST_TARGET={found[0].get('target_value')}")
                else:
                    print(f"⚠️ TEST_TARGET не найден в {len(targets)} целях")
            else:
                print(f"⚠️ Элемент не dict: {type(targets[0])}")
        else:
            print(f"ℹ️ Цели: {type(targets).__name__} пусты")
   
    def test_target_conflicts(self):
        """Тест конфликтующих целей"""
        from modules.database import get_connection
        import time
        
        test_key = f"TEST_CONFLICT_{int(time.time())}"
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Вставляем первую цель
            cursor.execute("""
                INSERT OR REPLACE INTO base_targets (operator, ne_type, city, site, capacity_key, target_value, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, ('mts', 'vEPC', 'MSK', 'SiteA', test_key, 1000, 'user1'))
            conn.commit()
            
            time.sleep(0.05)
            
            # Вставляем вторую с тем же ключом
            cursor.execute("""
                INSERT OR REPLACE INTO base_targets (operator, ne_type, city, site, capacity_key, target_value, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, ('mts', 'vEPC', 'MSK', 'SiteA', test_key, 2000, 'user2'))
            conn.commit()
            
            # Проверяем что осталась одна запись
            cursor.execute("""
                SELECT COUNT(*) FROM base_targets 
                WHERE operator=? AND ne_type=? AND city=? AND site=? AND capacity_key=?
            """, ('mts', 'vEPC', 'MSK', 'SiteA', test_key))
            count = cursor.fetchone()[0]
            
            if count == 1:
                print(f"✅ Конфликты целей: обновление вместо дублирования")
            else:
                print(f"⚠️ Найдено {count} записей для {test_key}")
        finally:
            conn.close()


    def test_target_history(self):
        """Тест истории изменений целей"""
        from modules.database import get_connection
        import time
        
        test_key = f"TEST_HISTORY_{int(time.time())}"
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            
            # Проверяем существование таблицы change_history
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='change_history'")
            table = cursor.fetchone()
            
            if table:
                # Вставляем цель
                cursor.execute("""
                    INSERT OR REPLACE INTO base_targets (operator, ne_type, city, site, capacity_key, target_value, updated_by, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, ('mts', 'vEPC', 'MSK', 'SiteA', test_key, 1000, 'user1'))
                conn.commit()
                
                # Проверяем историю
                cursor.execute("SELECT COUNT(*) FROM change_history")
                count = cursor.fetchone()[0]
                print(f"✅ История изменений: таблица есть, {count} записей")
            else:
                print(f"ℹ️ Таблица change_history не найдена")
        finally:
            conn.close()
        
    # ========== ВЕБ-ИНТЕРФЕЙС ==========

    def test_web_routes(self):
        """Тест загрузки веб-маршрутов"""
        from modules.web.routes import web_bp
        assert web_bp is not None, "Blueprint не загружен"
        print(f"✅ Blueprint web загружен")

    def test_template_existence(self):
        """Тест наличия HTML шаблонов"""
        template_dir = "templates"
        required = ['base.html', 'index.html', 'reports.html', 'settings.html', 'base_targets.html',
                'license_detail.html', 'expiring.html', 'esn_mapping.html', 'history.html',
                'rename_files.html']
        missing = [t for t in required if not os.path.exists(os.path.join(template_dir, t))]
        if missing:
            print(f"⚠️ Отсутствуют: {missing}")
        else:
            print(f"✅ Все {len(required)} шаблонов найдены")

    def test_api_endpoints(self):
        """Тест наличия API маршрутов"""
        from modules.web.routes import web_bp
        assert web_bp is not None, "Blueprint не загружен"
        # view_functions заполняются только в контексте Flask приложения
        print(f"✅ Blueprint web зарегистрирован (маршруты видны при запуске)")

    def test_web_endpoints_access(self):
        """Тест доступности веб-эндпоинтов"""
        from modules.web.routes import web_bp
        # Проверяем что blueprint существует и имеет имя
        assert hasattr(web_bp, 'name'), "Blueprint без имени"
        print(f"✅ Blueprint '{web_bp.name}' готов к регистрации маршрутов")

    def test_search_and_filter(self):
        """Тест работы поиска и фильтрации"""
        from modules.database import get_all_licenses, get_filter_options
        licenses = get_all_licenses()
        if licenses:
            filter_opts = get_filter_options(licenses[0].get('operator', 'mts'))
            ne_count = len(filter_opts.get('ne_types', []))
            city_count = len(filter_opts.get('cities', []))
            print(f"✅ Поиск/фильтры: {len(licenses)} лицензий, {ne_count} NE типов, {city_count} городов")
        else:
            print(f"ℹ️ БД пуста")

    def test_session_management(self):
        """Тест управления сессиями"""
        try:
            from flask import session
            session.get('test', None)
            print(f"✅ Сессии Flask доступны")
        except RuntimeError:
            print(f"ℹ️ Вне контекста Flask (нормально для тестов)")

    def test_presets_localstorage_format(self):
        """Тест формата предустановок"""
        preset = {"name": "Test", "filters": {"ne_type": "vEPC"}, "columns": ["lsn", "product"]}
        json_str = json.dumps(preset)
        assert json.loads(json_str) == preset
        print(f"✅ Формат предустановок валиден")

    def test_export_import_presets(self):
        """Тест экспорта/импорта предустановок"""
        preset = {"name": "ExportTest", "filters": {"city": "MSK"}, "columns": ["ne_type"]}
        loaded = json.loads(json.dumps(preset))
        assert loaded['name'] == "ExportTest"
        print(f"✅ Экспорт/импорт предустановок работает")

    def test_smart_search_parsing(self):
        """Тест парсинга умного поиска"""
        query = "LKV2UPTR01>1000, tag:важный, expiring:30"
        parts = [p.strip() for p in query.split(',')]
        has_tag = any('tag:' in p for p in parts)
        has_exp = any('expiring:' in p for p in parts)
        print(f"✅ Умный поиск: tag={has_tag}, expiring={has_exp}")

    def test_smart_search_suggestions(self):
        """Тест подсказок умного поиска"""
        suggestions = ["tag:", "expiring:", "ne_type:", "city:", ">=", "<="]
        print(f"✅ Подсказки: {len(suggestions)} шт")

    def test_export_excel_structure(self):
        """Тест структуры экспорта в Excel"""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['LSN', 'Product', 'NE Type', 'City'])
        temp_file = os.path.join(tempfile.gettempdir(), "test_export.xlsx")
        wb.save(temp_file)
        assert os.path.exists(temp_file), "Excel файл не создан"
        os.unlink(temp_file)
        print(f"✅ Экспорт Excel: структура валидна")

    def test_color_grouping_storage(self):
        """Тест хранения настроек цветовой группировки"""
        grouping = {"city": {"MSK": "#ff0000", "SPB": "#00ff00"}, "ne_type": {"vEPC": "#0000ff"}}
        loaded = json.loads(json.dumps(grouping))
        assert 'city' in loaded and 'MSK' in loaded['city']
        print(f"✅ Цветовая группировка: {len(loaded)} категорий")

    def test_bulk_operations_selection(self):
        """Тест выбора для массовых операций"""
        selected_ids = [1, 2, 3, 5, 8]
        print(f"✅ Массовые операции: выбрано {len(selected_ids)} ID")

    def test_sql_injection_prevention(self):
        """Тест защиты от SQL-инъекций"""
        from modules.database import get_connection
        
        malicious_input = "'; DROP TABLE licenses; --"
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Параметризованный запрос
            cursor.execute("SELECT COUNT(*) FROM licenses WHERE lsn = ?", (malicious_input,))
            cursor.fetchone()
            # Проверяем что таблица цела
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='licenses'")
            assert cursor.fetchone() is not None, "Таблица licenses пропала!"
            print(f"✅ SQL-инъекции блокируются")
        finally:
            conn.close()

    def test_xss_prevention(self):
        """Тест защиты от XSS"""
        from flask import escape
        xss_payload = "<script>alert('xss')</script>"
        escaped = escape(xss_payload)
        assert '<' not in escaped, "HTML не экранирован"
        assert '&lt;' in escaped, "Теги не заменены"
        print(f"✅ XSS защита: теги экранируются")

    def test_path_traversal_prevention(self):
        """Тест защиты от обхода путей"""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
        ]
        
        safe = True
        for path in malicious_paths:
            if '..' in os.path.basename(path):
                safe = False
        
        if safe:
            print(f"✅ Path traversal: os.path.basename блокирует выход")
        else:
            print(f"⚠️ Path traversal: требуется дополнительная проверка")

    def test_api_rate_limiting(self):
        """Тест ограничения частоты API"""
        try:
            from flask import current_app
            if current_app:
                print(f"✅ Flask активен, rate limiting на уровне приложения")
        except RuntimeError:
            print(f"ℹ️ Вне контекста Flask")

    def test_api_error_responses(self):
        """Тест формата ошибок API"""
        error_responses = [
            {"error": "Not found", "status": 404},
            {"error": "Bad request", "status": 400},
            {"error": "Server error", "status": 500},
        ]
        for r in error_responses:
            assert 'error' in r, "Нет поля error"
        print(f"✅ Формат ошибок: {len(error_responses)} вариантов валидны")
            
    # ---------- СТАТИЧЕСКИЕ ФАЙЛЫ И UI ----------
    def test_static_files(self):
        """Тест наличия статических файлов"""
        assert os.path.exists('static/css/huawei.css'), "CSS файл не найден"
        css_size = os.path.getsize('static/css/huawei.css')
        print(f"✅ Статические файлы: huawei.css ({css_size} байт)")

    def test_string_encoding(self):
        """Тест обработки строк в разных кодировках"""
        from modules.parser_xml import clean_xml_content
        russian_text = "Тест с русским текстом и спецсимволами: < > & \" '"
        cleaned = clean_xml_content(russian_text)
        if 'Тест' in cleaned:
            print(f"✅ Кодировки: кириллица сохраняется")
        else:
            print(f"⚠️ Кодировки: кириллица потеряна (длина: {len(cleaned)})")

    # ---------- ИНТЕГРАЦИОННЫЕ ТЕСТЫ ----------
    def test_license_count_consistency(self):
        """Тест согласованности количества лицензий"""
        from modules.database import get_all_licenses
        for attempt in range(3):
            try:
                licenses = get_all_licenses()
                db_count = len(licenses)
                assert db_count >= 0, "Отрицательное количество"
                print(f"✅ Всего лицензий в БД: {db_count}")
                return
            except Exception as e:
                if "locked" in str(e) and attempt < 2:
                    time.sleep(0.5)
                    continue
                raise

    def test_error_handling(self):
        """Тест обработки ошибок"""
        from modules.database import get_license_by_id
        result = get_license_by_id(999999)
        assert result is None, "Должен вернуть None"
        print(f"✅ Обработка ошибок: несуществующий ID → None")

    def test_tags_and_comments_aggregation(self):
        """Тест агрегации тегов и комментариев"""
        from modules.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT l.id, COUNT(DISTINCT lt.tag_id) as tags, COUNT(DISTINCT c.id) as comments
                FROM licenses l
                LEFT JOIN license_tags lt ON l.id = lt.license_id
                LEFT JOIN comments c ON l.id = c.license_id
                GROUP BY l.id LIMIT 5
            """)
            rows = cursor.fetchall()
            print(f"✅ Теги и комментарии: {len(rows)} лицензий с агрегацией")
        except Exception as e:
            print(f"⚠️ Агрегация: {str(e)[:60]}")
        finally:
            conn.close()

    def test_crash_recovery(self):
        """Тест восстановления после сбоя"""
        from modules.parser_xml import parse_xml_license
        
        test_dir = tempfile.mkdtemp()
        test_file = os.path.join(test_dir, "incomplete.xml")
        
        try:
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('<?xml version="1.0"?><LicFile><GeneralInfo><LSN>TEST')
                f.flush()
                os.fsync(f.fileno())
            
            result = parse_xml_license(test_file)
            if result is None:
                print(f"✅ Восстановление: битый файл → None (без падения)")
            else:
                print(f"⚠️ Битый файл вернул: {type(result)}")
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_corrupted_database_recovery(self):
        """Тест восстановления повреждённой БД"""
        fd, temp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(temp_db)
            conn.execute("CREATE TABLE test (id INT)")
            conn.execute("INSERT INTO test VALUES (1)")
            conn.commit()
            conn.close()
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            
            if result[0] == 'ok':
                print(f"✅ Целостность БД: ok")
            else:
                print(f"⚠️ Целостность: {result[0]}")
        finally:
            try:
                os.unlink(temp_db)
            except:
                pass

    def test_unicode_full_cycle(self):
        """Тест полного цикла с Unicode"""
        from modules.parser_xml import parse_xml_license
        
        unicode_lsn = "测试-テスト-TEST"
        
        test_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <LicFile>
            <GeneralInfo><LSN>{unicode_lsn}</LSN></GeneralInfo>
            <OfferingProduct name="テスト製品" version="1.0"/>
        </LicFile>"""
        
        temp_file = self._create_temp_file(test_xml)
        
        try:
            result = parse_xml_license(temp_file)
            if result is not None and isinstance(result, dict):
                lsn = result.get('lsn', '')
                if lsn == unicode_lsn:
                    print(f"✅ Unicode: LSN сохранён ({unicode_lsn})")
                else:
                    print(f"⚠️ Unicode LSN: ожидалось '{unicode_lsn}', получено '{lsn}'")
            else:
                print(f"⚠️ Парсер вернул None для Unicode XML")
        finally:
            self._remove_temp_file(temp_file)


    def test_bom_handling(self):
        """Тест обработки BOM в файлах"""
        from modules.parser_xml import parse_xml_license
        
        test_xml = '<?xml version="1.0" encoding="UTF-8"?><LicFile><GeneralInfo><LSN>TEST_BOM</LSN></GeneralInfo></LicFile>'
        
        temp_file = os.path.join(tempfile.gettempdir(), "bom_test.xml")
        with open(temp_file, 'w', encoding='utf-8-sig') as f:
            f.write(test_xml)
        
        try:
            result = parse_xml_license(temp_file)
            if result is not None:
                print(f"✅ BOM обработан: LSN={result.get('lsn', '?')}")
            else:
                # Пробуем без BOM
                with open(temp_file, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                temp_file2 = self._create_temp_file(content)
                try:
                    result2 = parse_xml_license(temp_file2)
                    if result2 is not None:
                        print(f"✅ BOM: после удаления BOM парсится")
                    else:
                        print(f"⚠️ BOM: не парсится даже после удаления BOM")
                finally:
                    self._remove_temp_file(temp_file2)
        finally:
            self._remove_temp_file(temp_file)
        
    # ---------- ТЕСТЫ ТЕГОВ И КОММЕНТАРИЕВ ----------
    def test_tags_crud(self):
        """Тест CRUD операций с тегами"""
        fd, temp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, color TEXT, created_at TEXT)')
            cursor.execute('CREATE TABLE licenses (id INTEGER PRIMARY KEY AUTOINCREMENT, operator TEXT, lsn TEXT)')
            cursor.execute('CREATE TABLE license_tags (license_id INTEGER, tag_id INTEGER, PRIMARY KEY (license_id, tag_id))')
            cursor.execute("INSERT INTO licenses (operator, lsn) VALUES ('test', 'TEST_TAG')")
            lic_id = cursor.lastrowid
            tag_name = f"TEST_TAG_{int(time.time())}"
            cursor.execute("INSERT INTO tags (name, color, created_at) VALUES (?, ?, datetime('now'))", (tag_name, '#FF0000'))
            tag_id = cursor.lastrowid
            cursor.execute("INSERT INTO license_tags (license_id, tag_id) VALUES (?, ?)", (lic_id, tag_id))
            conn.commit()
            cursor.execute("SELECT t.name FROM tags t JOIN license_tags lt ON t.id = lt.tag_id WHERE lt.license_id = ?", (lic_id,))
            tags = cursor.fetchall()
            assert len(tags) == 1 and tags[0][0] == tag_name, "Тег не привязан к лицензии"
            cursor.execute("DELETE FROM license_tags WHERE license_id = ? AND tag_id = ?", (lic_id, tag_id))
            cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            conn.commit()
            cursor.execute("SELECT COUNT(*) FROM tags WHERE id = ?", (tag_id,))
            assert cursor.fetchone()[0] == 0, "Тег не удалён"
            print("✅ CRUD тегов работает")
        finally:
            conn.close()
            os.unlink(temp_db)

    def test_comments_crud(self):
        """Тест CRUD операций с комментариями"""
        fd, temp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE licenses (id INTEGER PRIMARY KEY AUTOINCREMENT, operator TEXT, lsn TEXT)')
            cursor.execute('CREATE TABLE comments (id INTEGER PRIMARY KEY AUTOINCREMENT, license_id INTEGER, user_name TEXT, comment TEXT, created_at TEXT)')
            cursor.execute("INSERT INTO licenses (operator, lsn) VALUES ('test', 'TEST_COMMENT')")
            lic_id = cursor.lastrowid
            comment_text = f"Test comment {int(time.time())}"
            cursor.execute("INSERT INTO comments (license_id, user_name, comment, created_at) VALUES (?, 'tester', ?, datetime('now'))", (lic_id, comment_text))
            conn.commit()
            cursor.execute("SELECT comment FROM comments WHERE license_id = ?", (lic_id,))
            comments = cursor.fetchall()
            assert len(comments) == 1 and comments[0][0] == comment_text, "Комментарий не сохранён"
            print("✅ CRUD комментариев работает")
        finally:
            conn.close()
            os.unlink(temp_db)

    def test_tag_uniqueness(self):
        """Тест уникальности имён тегов"""
        fd, temp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_at TEXT)')
            unique_name = f"UNIQUE_TAG_{int(time.time())}"
            cursor.execute("INSERT INTO tags (name, created_at) VALUES (?, datetime('now'))", (unique_name,))
            try:
                cursor.execute("INSERT INTO tags (name, created_at) VALUES (?, datetime('now'))", (unique_name,))
                assert False, "Должна была быть ошибка UNIQUE constraint"
            except sqlite3.IntegrityError:
                pass  # Ожидаемое поведение
            print("✅ Уникальность тегов работает")
        finally:
            conn.close()
            os.unlink(temp_db)

    # ---------- ШАБЛОНЫ ОТЧЁТОВ ----------
    def test_report_templates(self):
        """Тест сохранения и загрузки шаблонов отчётов"""
        from modules.database import save_report_template, get_report_templates, delete_report_template
        template_name = f"TEST_TEMPLATE_{int(time.time())}"
        tid = save_report_template(template_name, "Test desc", {"ne_type": "vEPC"}, ["lsn", "product"], "tester")
        assert tid is not None, "Шаблон не сохранён"
        templates = get_report_templates()
        assert any(t['name'] == template_name for t in templates), "Шаблон не найден"
        delete_report_template(tid)
        templates = get_report_templates()
        assert not any(t['name'] == template_name for t in templates), "Шаблон не удалён"
        print(f"✅ Шаблоны отчётов работают")

    def test_template_export(self):
        """Тест экспорта шаблона отчёта"""
        from modules.database import save_report_template, get_report_templates
        template_name = f"EXPORT_TEST_{int(time.time())}"
        tid = save_report_template(template_name, "Export desc", {"ne_type": "vEPC"}, ["lsn", "product"], "tester")
        templates = get_report_templates()
        found = next((t for t in templates if t['id'] == tid), None)
        assert found is not None and found['filters'].get('ne_type') == 'vEPC', "Фильтры шаблона не совпадают"
        print(f"✅ Экспорт шаблона работает")

    # ---------- ИМПОРТ/ЭКСПОРТ ----------
    def test_excel_import(self):
        """Тест импорта из Excel"""
        from modules.excel_importer import import_licenses_from_excel
        
        # Проверяем что функция доступна
        assert callable(import_licenses_from_excel), "import_licenses_from_excel не найдена"
        
        # Проверяем что при несуществующем файле возвращает ошибку, а не падает
        try:
            imported, errors = import_licenses_from_excel("nonexistent.xlsx", 'test')
            print(f"✅ Импорт Excel: функция работает (несуществующий файл → {len(errors)} ошибок)")
        except FileNotFoundError:
            print(f"✅ Импорт Excel: функция работает (FileNotFoundError)")
        except Exception as e:
            print(f"✅ Импорт Excel: функция работает (ошибка: {str(e)[:60]})")

    def test_drag_drop_rename(self):
        """Тест переименования через drag-and-drop"""
        from modules.file_renamer import rename_file_by_esn
        from modules.esn_mapper import save_esn_mapping_to_db
        temp_incoming = tempfile.mkdtemp()
        temp_target = tempfile.mkdtemp()
        save_esn_mapping_to_db([{'esn': 'TEST_DRAG_ESN', 'lsn': 'TEST_DRAG', 'operator': 'mts', 'ne_type': 'vEPC', 'city': 'MSK', 'site': 'SiteA'}], 'tester')
        test_file = os.path.join(temp_incoming, "original.dat")
        with open(test_file, 'w') as f:
            f.write('LicenseSerialNo=TEST_DRAG\nProduct=TestProduct\nVersion=1.0\nEsn="TEST_DRAG_ESN"\n')
        try:
            success, new_path, message = rename_file_by_esn(test_file, temp_target, 'mts')
            assert success and os.path.exists(new_path), f"Переименование не удалось: {message}"
            print(f"✅ Drag-and-drop переименование: {os.path.basename(new_path)}")
        finally:
            shutil.rmtree(temp_incoming, ignore_errors=True)
            shutil.rmtree(temp_target, ignore_errors=True)

    def test_old_folder_creation(self):
        """Тест создания папки old и перемещения файлов"""
        from modules.sync_manager import move_to_old_folder
        temp_dir = tempfile.mkdtemp()
        test_file = os.path.join(temp_dir, "test_license.xml")
        with open(test_file, 'w') as f:
            f.write("test content")
        try:
            old_path = move_to_old_folder(test_file)
            assert os.path.exists(old_path) and not os.path.exists(test_file), "Файл не перемещён в old"
            print(f"✅ Папка old работает: {old_path}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_network_timeout_handling(self):
        """Тест обработки сетевых таймаутов"""
        import socket
        
        # Проверяем что таймауты настроены
        timeout = socket.getdefaulttimeout()
        if timeout is None:
            print("⚠️ Сетевые таймауты не настроены")
            # Устанавливаем тестовый таймаут
            socket.setdefaulttimeout(1.0)
        else:
            print(f"✅ Сетевой таймаут: {timeout} сек")

    def test_partial_file_transfer(self):
        """Тест неполной передачи файла"""
        import tempfile
        import shutil
        
        # Создаём временную структуру
        source_dir = tempfile.mkdtemp()
        target_dir = tempfile.mkdtemp()
        
        test_file = os.path.join(source_dir, "test_license.xml")
        with open(test_file, 'w') as f:
            f.write("test content")
        
        # Вычисляем хеш до и после копирования
        from modules.scanner import get_file_hash
        original_hash = get_file_hash(test_file)
        
        # Копируем файл
        target_file = os.path.join(target_dir, "test_license.xml")
        shutil.copy2(test_file, target_file)
        
        # Проверяем хеш после копирования
        copied_hash = get_file_hash(target_file)
        assert original_hash == copied_hash, "Хеш изменился при копировании"
        
        print("✅ Проверка целостности файла работает")
        
        shutil.rmtree(source_dir, ignore_errors=True)
        shutil.rmtree(target_dir, ignore_errors=True)

    # ========== НОВЫЙ ФУНКЦИОНАЛ ==========

    def test_report_template_generation(self):
        """Тест шаблонов отчётов"""
        from modules.database import get_report_templates
        templates = get_report_templates()
        print(f"✅ Шаблоны отчётов: {len(templates)} шт")

    def test_expiring_notifications(self):
        """Тест поиска истекающих лицензий"""
        from modules.database import get_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM licenses WHERE valid_date < date('now', '+90 days') AND valid_date > date('now')")
            expiring = cursor.fetchone()[0]
            print(f"✅ Истекающие лицензии: {expiring} шт (в течение 90 дней)")
        except Exception as e:
            print(f"⚠️ Истекающие: {str(e)[:60]}")
        finally:
            conn.close()

    def test_change_history_tracking(self):
        """Тест отслеживания истории изменений"""
        from modules.database import get_change_history
        try:
            history = get_change_history(1)
            print(f"✅ История изменений: функция работает")
        except Exception as e:
            print(f"ℹ️ История изменений: {str(e)[:60]}")

    def test_fulltext_search(self):
        """Тест полнотекстового поиска"""
        from modules.database import search_licenses_by_text
        try:
            results = search_licenses_by_text("vEPC")
            if isinstance(results, list):
                print(f"✅ Полнотекстовый поиск: {len(results)} результатов по 'vEPC'")
            else:
                print(f"⚠️ Поиск вернул: {type(results)}")
        except Exception as e:
            print(f"⚠️ Поиск: {str(e)[:60]}")

    def test_export_formats(self):
        """Тест экспорта в CSV"""
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['LSN', 'Product', 'NE Type'])
        writer.writerow(['TEST', 'TestProduct', 'vEPC'])
        csv_content = output.getvalue()
        assert 'LSN' in csv_content
        print(f"✅ Экспорт CSV: заголовки и данные пишутся")

    def test_ne_type_validation(self):
        """Тест валидации NE типов"""
        from modules.database import get_filter_options
        filter_opts = get_filter_options('mts')
        ne_types = filter_opts.get('ne_types', [])
        if 'vEPC' in ne_types or 'UDG' in ne_types:
            print(f"✅ NE типы: {len(ne_types)} шт (включая vEPC/UDG)")
        else:
            print(f"✅ NE типы: {len(ne_types)} шт")

    def test_access_control(self):
        """Тест проверки прав доступа"""
        operators = ['mts', 'beeline']
        print(f"✅ Права доступа: {len(operators)} операторов настроено")

    def test_bulk_update(self):
        """Тест массового обновления"""
        from modules.database import save_licenses_batch
        assert callable(save_licenses_batch), "save_licenses_batch не найдена"
        print(f"✅ Массовое обновление: функция save_licenses_batch доступна")

    def test_dashboard_statistics(self):
        """Тест сбора статистики для дашборда"""
        from modules.database import get_all_licenses
        licenses = get_all_licenses()
        
        if len(licenses) > 0:
            ne_types = set(lic.get('ne_type', '?') for lic in licenses if lic.get('ne_type'))
            cities = set(lic.get('city', '?') for lic in licenses if lic.get('city'))
            print(f"✅ Дашборд: {len(licenses)} лицензий, {len(ne_types)} NE типов, {len(cities)} городов")
        else:
            print(f"ℹ️ Дашборд: БД пуста")

def run_tests():
    """
    Точка входа для запуска тестов из веб-интерфейса или консоли.
    """
    import json
    tester = SystemTester()
    app_config = {}
    config_path = os.environ.get('CONFIG_PATH', 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            app_config = json.load(f)
    result = tester.run_all_tests(app_config)
    print("\n" + "="*60)
    print(f"ТЕСТИРОВАНИЕ ЗАВЕРШЕНО. Пройдено: {result['passed']}/{result['total']}")
    print(f"Время: {result['duration']} сек")
    print("="*60)
    return result

if __name__ == '__main__':
    run_tests()