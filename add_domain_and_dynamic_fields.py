# migrations/add_domain_and_dynamic_fields.py
"""
Миграция БД: добавляем колонку domain и систему динамических полей
Запуск: python migrations/add_domain_and_dynamic_fields.py
"""

import sqlite3
import os
import sys
import json
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import get_connection, get_db_path

def migrate():
    """Выполняет миграцию БД"""
    print("=" * 60)
    print("Миграция БД: добавление domain и динамических полей")
    print("=" * 60)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    changes = []
    
    # 1. Добавляем колонку domain в таблицу licenses
    try:
        cursor.execute("ALTER TABLE licenses ADD COLUMN parsed_cache TEXT")
        changes.append("✅ Добавлена колонка parsed_cache в licenses")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            changes.append("ℹ️ Колонка parsed_cache уже есть")
        else:
            raise
    
    # 2. Добавляем колонку domain в таблицу esn_mapping
    try:
        cursor.execute("ALTER TABLE esn_mapping ADD COLUMN domain TEXT")
        changes.append("✅ Добавлена колонка domain в esn_mapping")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            changes.append("ℹ️ Колонка domain уже есть в esn_mapping")
        else:
            raise
    
    # 3. Создаём таблицу динамических колонок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dynamic_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            column_name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            rule_id TEXT,
            capacity_key TEXT,
            aggregation_strategy TEXT DEFAULT 'sum',
            join_separator TEXT DEFAULT ', ',
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    changes.append("✅ Создана таблица dynamic_columns")
    
    # 4. Создаём таблицу значений динамических полей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dynamic_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            column_id INTEGER NOT NULL,
            value TEXT,
            FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
            FOREIGN KEY (column_id) REFERENCES dynamic_columns(id) ON DELETE CASCADE,
            UNIQUE(license_id, column_id)
        )
    ''')
    changes.append("✅ Создана таблица dynamic_values")
    
    # 5. Обновляем уникальный индекс с учётом domain
    try:
        cursor.execute("DROP INDEX IF EXISTS idx_licenses_unique")
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_unique 
            ON licenses(operator, domain, ne_type, city, site, year, lsn)
        ''')
        changes.append("✅ Обновлён уникальный индекс с domain")
    except Exception as e:
        changes.append(f"⚠️ Не удалось обновить индекс: {e}")
    
    conn.commit()
    conn.close()
    
    # Выводим результат
    print("\n".join(changes))
    print("\n🎉 Миграция завершена успешно!")
    
    # Создаём extraction_rules.json если его нет
    create_default_rules()


def create_default_rules():
    """Создаёт файл с правилами извлечения по умолчанию"""
    rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'extraction_rules.json')
    
    if os.path.exists(rules_path):
        print("ℹ️ extraction_rules.json уже существует")
        return
    
    default_rules = {
        "version": 1,
        "created_at": datetime.now().isoformat(),
        "rules": {
            "esn": {
                "display_name": "ESN",
                "regex_dat": "r\"Esn[=:]\\s*\\\"?([^\\\"]+)\\\"?\"",
                "xpath_xml": ".//ESN/text()",
                "value_type": "text",
                "aggregation_strategy": "first",
                "join_separator": ", "
            },
            "lsn": {
                "display_name": "LSN",
                "regex_dat": "r\"LicenseSerialNo[=:]\\s*(\\S+)\"",
                "xpath_xml": ".//LSN/text()",
                "value_type": "text",
                "aggregation_strategy": "first",
                "join_separator": ", "
            },
            "node": {
                "display_name": "Узел",
                "regex_dat": "r\"Product[=:]\\s*(\\S+)\"",
                "xpath_xml": ".//Node/text()",
                "value_type": "text",
                "aggregation_strategy": "first",
                "join_separator": ", "
            },
            "create_time": {
                "display_name": "Дата создания",
                "regex_dat": "r\"CreatedTime[=:]\\s*([0-9\\-\\s:]+)\"",
                "xpath_xml": ".//CreateTime/text()",
                "value_type": "date",
                "aggregation_strategy": "first",
                "join_separator": ", "
            },
            "product": {
                "display_name": "Продукт",
                "regex_dat": "r\"Product[=:]\\s*(\\S+)\"",
                "xpath_xml": ".//OfferingProduct/@name",
                "value_type": "text",
                "aggregation_strategy": "first",
                "join_separator": ", "
            },
            "version": {
                "display_name": "Версия",
                "regex_dat": "r\"Version[=:]\\s*(\\S+)\"",
                "xpath_xml": ".//OfferingProduct/@version",
                "value_type": "text",
                "aggregation_strategy": "first",
                "join_separator": ", "
            },
            "tech_park": {
                "display_name": "Технологическая площадка",
                "regex_dat": "r\"TechPark[=:]\\s*([^\\\"\\n]+)\"",
                "xpath_xml": ".//Node[@type='TechPark']/text()",
                "value_type": "text",
                "aggregation_strategy": "first",
                "join_separator": ", "
            }
        }
    }
    
    with open(rules_path, 'w', encoding='utf-8') as f:
        json.dump(default_rules, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Создан {rules_path} с правилами по умолчанию")


def rollback():
    """Откат миграции (только для разработки)"""
    print("⚠️ Откат миграции...")
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS dynamic_values")
    cursor.execute("DROP TABLE IF EXISTS dynamic_columns")
    
    conn.commit()
    conn.close()
    
    print("✅ Таблицы dynamic_columns и dynamic_values удалены")
    print("ℹ️ Колонки domain не удаляются автоматически. Для отката восстановите БД из бэкапа.")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollback', action='store_true', help='Откатить миграцию')
    args = parser.parse_args()
    
    if args.rollback:
        rollback()
    else:
        migrate()