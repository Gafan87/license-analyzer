# migrations/add_spart_columns.py
import sqlite3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import get_connection

def migrate_spart():
    conn = get_connection()
    cursor = conn.cursor()
    
    columns = [
        ('is_spart', 'INTEGER DEFAULT 0'),
        ('parent_key', 'TEXT'),
        ('part_number', 'TEXT'),
        ('feature_description', 'TEXT'),
        ('dimensioning', 'TEXT'),
        ('sort_order', 'INTEGER')
    ]
    
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE capacity_aggregated ADD COLUMN {col_name} {col_type}")
            print(f"✅ Добавлена колонка {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"ℹ️ Колонка {col_name} уже существует")
            else:
                raise
    
    conn.commit()
    conn.close()
    print("🎉 Миграция завершена")

if __name__ == '__main__':
    migrate_spart()