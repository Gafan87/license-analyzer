# migrate_targets.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from modules.database import get_connection

def migrate():
    print("🔄 Запуск миграции...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # ========== СОЗДАЁМ ТАБЛИЦЫ, ЕСЛИ ИХ НЕТ ==========
    
    # Таблица domain_targets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            domain TEXT,
            type TEXT,
            unit TEXT,
            target_key TEXT,
            city TEXT,
            value REAL,
            sharing INTEGER,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    print("✅ Таблица domain_targets создана (или уже существует)")
    
    # Таблица license_targets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            target_key TEXT,
            city TEXT,
            ne_type TEXT,
            capacity_key TEXT,
            target_value REAL,
            item_type TEXT DEFAULT 'target'
        )
    ''')
    print("✅ Таблица license_targets создана (или уже существует)")
    
    conn.commit()
    conn.close()
    print("✅ Миграция завершена")

if __name__ == '__main__':
    migrate()