import os
import sys
import json
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.web.routes import web_bp
from modules.logger import setup_logging
from modules.database import set_db_path, init_local_db

# Создаём приложение
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'license-analyzer-secret-key-2024')

# ========== ЗАГРУЗКА КОНФИГУРАЦИИ ==========

CONFIG_PATH = os.environ.get('CONFIG_PATH', 'config.json')

# Функция для создания конфига по умолчанию
def create_default_config():
    """Создаёт файл конфигурации по умолчанию"""
    default_config = {
        "log_level": "INFO",
        "network_storage_path": "",
        "ne_type_mapping_file": "mapping/ne_type_mapping.xlsx",
        "operators": [
            {
                "name": "mts",
                "title": "МТС",
                "local_scan_path": "",
                "incoming_folder": ""
            }
        ]
    }
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, ensure_ascii=False, indent=2)
    return default_config

# Загружаем конфиг
if not os.path.exists(CONFIG_PATH):
    print(f"⚠️ Файл {CONFIG_PATH} не найден. Создаю конфиг по умолчанию...")
    config = create_default_config()
    print(f"✅ Создан {CONFIG_PATH}")
else:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"✅ Загружен конфиг: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга {CONFIG_PATH}: {e}")
        print("🔄 Создаю конфиг по умолчанию...")
        config = create_default_config()

# Применяем конфигурацию
app.config.update(config)
app.config['OPERATORS'] = config.get('operators', [])
app.config['LOG_LEVEL'] = config.get('log_level', 'INFO')
app.config['network_storage_path'] = config.get('network_storage_path', '')
app.config['NE_TYPE_MAPPING_FILE'] = config.get('ne_type_mapping_file', 'mapping/ne_type_mapping.xlsx')
app.config['MAPPING_PATH'] = config.get('mapping_path', '')
app.config['LICENSE_DETAILS_PATH'] = config.get('license_details_path', '')

print(f"📋 Загружено операторов: {len(app.config['OPERATORS'])}")
for op in app.config['OPERATORS']:
    print(f"   - {op.get('name')}: {op.get('title')}")
print(f"📁 NE Type маппинг: {app.config['NE_TYPE_MAPPING_FILE']}")

# ========== ЗАГРУЗКА ПРАВИЛ ИЗВЛЕЧЕНИЯ ==========

EXTRACTION_RULES_PATH = os.environ.get('EXTRACTION_RULES_PATH', 'extraction_rules.json')

if not os.path.exists(EXTRACTION_RULES_PATH):
    print(f"⚠️ Файл {EXTRACTION_RULES_PATH} не найден. Будет создан при миграции.")
    app.config['EXTRACTION_RULES'] = {'rules': {}, 'version': 1}
else:
    try:
        with open(EXTRACTION_RULES_PATH, 'r', encoding='utf-8') as f:
            app.config['EXTRACTION_RULES'] = json.load(f)
        rules_count = len(app.config['EXTRACTION_RULES'].get('rules', {}))
        print(f"✅ Загружено {rules_count} правил из {EXTRACTION_RULES_PATH}")
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга {EXTRACTION_RULES_PATH}: {e}")
        app.config['EXTRACTION_RULES'] = {'rules': {}, 'version': 1}

# ========== НАСТРОЙКА БАЗЫ ДАННЫХ ==========

DB_PATH = os.environ.get('DB_PATH', 'local_licenses.db')

# Создаём директорию для БД если нужно
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# Устанавливаем путь к БД и инициализируем
set_db_path(DB_PATH)
init_local_db()
print(f"✅ База данных: {DB_PATH}")

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========

log_level = app.config.get('LOG_LEVEL', 'INFO')
setup_logging(log_level)
logger = logging.getLogger(__name__)

# ========== РЕГИСТРАЦИЯ МАРШРУТОВ ==========

app.register_blueprint(web_bp)

# ========== ДОПОЛНИТЕЛЬНЫЕ МАРШРУТЫ ==========

@app.route('/style_guide')
def style_guide():
    """Страница гайдлайна стилей"""
    return render_template('style_guide.html', 
                         current_operator='',
                         current_operator_title='Гайдлайн')


with app.app_context():
    from modules.capacity_mapper import load_ne_type_mapping
    load_ne_type_mapping()
    print("✅ Маппинг NE Type загружен")

# ========== ЗАПУСК ==========

if __name__ == '__main__':
    print("=" * 60)
    print("Анализатор лицензий Huawei (с динамическими полями)")
    print("=" * 60)
    print(f"Путь к БД: {DB_PATH}")
    print(f"Сетевое хранилище: {app.config.get('network_storage_path', 'не указано')}")
    print(f"NE Type маппинг: {app.config.get('NE_TYPE_MAPPING_FILE', 'не указан')}")
    print(f"Уровень логирования: {log_level}")
    print(f"Правил извлечения: {len(app.config['EXTRACTION_RULES'].get('rules', {}))}")
    print(f"Операторов: {len(app.config['OPERATORS'])}")
    print("=" * 60)
    print("ЗАПУСК ВЕБ-ИНТЕРФЕЙСА")
    print("=" * 60)
    print("Откройте в браузере: http://127.0.0.1:5000")
    print("=" * 60)
    
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    try:
        app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        print("\n🛑 Приложение остановлено")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        raise