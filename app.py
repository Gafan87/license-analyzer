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

# ========== ФУНКЦИЯ ДЛЯ АВТОМАТИЧЕСКОЙ ЗАГРУЗКИ ЦЕЛЕЙ ==========
def auto_load_and_compute_targets():
    """Автоматически загружает цели из Excel и вычисляет их при старте (упрощённая версия)"""
    from modules.capacity_mapper import load_targets_from_excel, compute_license_targets
    from modules.database import get_connection
    import os
    
    targets_file = app.config.get('targets_file', '')
    if not targets_file or not os.path.exists(targets_file):
        return False
    
    # Проверяем, есть ли уже цели в БД (чтобы не пересчитывать при каждом запуске)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM license_targets")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count > 0:
        print(f"✅ Цели уже загружены ({count} записей). Для пересчёта нажмите кнопку.")
        return True
    
    print("🔄 Первичная загрузка целей...")
    
    network_storage_path = app.config.get('network_storage_path', '')
    operators = app.config.get('OPERATORS', [])
    
    # Загружаем цели один раз для всех операторов
    all_targets = []
    for op in operators:
        operator_name = op.get('name')
        targets = load_targets_from_excel(targets_file, operator_name)
        if targets:
            all_targets.extend(targets)
    
    if not all_targets:
        return False
    
    # Получаем уникальные NE типы
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ne_type, domain FROM licenses WHERE ne_type IS NOT NULL AND ne_type != ''")
    ne_types = cursor.fetchall()
    conn.close()
    
    if not ne_types:
        return False
    
    total_results = 0
    
    for ne_type, domain in ne_types:
        # Загружаем структуру один раз для каждого NE типа
        from modules.capacity_mapper import load_full_capacity_list
        capacity_list = load_full_capacity_list(domain, network_storage_path, ne_type)
        if not capacity_list:
            continue
        
        # Вычисляем цели для всех операторов сразу
        for op in operators:
            operator_name = op.get('name')
            results = compute_license_targets(all_targets, capacity_list, operator_name)
            
            if results:
                with get_connection() as conn:
                    cursor = conn.cursor()
                    for r in results:
                        cursor.execute("""
                            INSERT OR REPLACE INTO license_targets 
                            (operator, target_key, city, ne_type, capacity_key, target_value)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (r['operator'], r['target_key'], r['city'], r['ne_type'], 
                              r['capacity_key'], r['target_value']))
                    conn.commit()
                    total_results += len(results)
    
    print(f"✅ Загружено {total_results} целей")
    return True
# ========== ЗАГРУЗКА МАППИНГА NE TYPE ==========

# ========== ПРОСТАЯ ИНИЦИАЛИЗАЦИЯ ==========
with app.app_context():
    # Загружаем маппинг NE Type (тихо)
    from modules.capacity_mapper import load_ne_type_mapping
    load_ne_type_mapping()
    
    # Быстрая проверка целей (без подробных логов)
    try:
        targets_file = app.config.get('targets_file', '')
        if targets_file and os.path.exists(targets_file):
            from modules.database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM license_targets")
            count = cursor.fetchone()[0]
            conn.close()
            
            if count == 0:
                print("🔄 Первичная загрузка целей (тихо)...")
                auto_load_and_compute_targets()
            else:
                print(f"✅ Цели уже загружены ({count} записей)")
        else:
            print("⚠️ Файл целей не указан или не найден")
    except Exception as e:
        print(f"⚠️ Пропускаем загрузку целей: {e}")

print("✅ Инициализация завершена")

# ========== ЗАПУСК ==========

# ========== ЗАПУСК ==========

if __name__ == '__main__':
    print("=" * 50)
    print("Анализатор лицензий Huawei")
    print("=" * 50)
    print(f"БД: {DB_PATH}")
    print(f"Операторов: {len(app.config['OPERATORS'])}")
    print("=" * 50)
    
    # Быстрая инициализация (без долгих операций)
    with app.app_context():
        from modules.capacity_mapper import load_ne_type_mapping
        load_ne_type_mapping()
    
    print("🌐 Запуск сервера...")
    print("Откройте: http://127.0.0.1:5000")
    print("=" * 50)
    
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    try:
        app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        print("\n🛑 Остановлено")