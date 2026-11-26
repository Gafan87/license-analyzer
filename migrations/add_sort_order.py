# add_sort_order.py
import sqlite3
import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.database import get_connection

def add_sort_order():
    print("🔄 Добавление колонки sort_order...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE domain_targets ADD COLUMN sort_order INTEGER DEFAULT 0")
        print("✅ Колонка sort_order добавлена в domain_targets")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⏭️ Колонка sort_order уже существует")
        else:
            print(f"⚠️ Ошибка: {e}")
    
    try:
        cursor.execute("ALTER TABLE license_targets ADD COLUMN item_type TEXT DEFAULT 'target'")
        print("✅ Колонка item_type добавлена в license_targets")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⏭️ Колонка item_type уже существует")
        else:
            print(f"⚠️ Ошибка: {e}")
    
    conn.commit()
    conn.close()
    print("✅ Готово")

if __name__ == '__main__':
    add_sort_order()