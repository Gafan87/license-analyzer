# add_columns_direct.py
import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_licenses.db')

if not os.path.exists(db_path):
    db_path = 'local_licenses.db'

print(f"БД: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Добавляем sort_order в domain_targets
try:
    cursor.execute("ALTER TABLE domain_targets ADD COLUMN sort_order INTEGER DEFAULT 0")
    print("✅ sort_order добавлен")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e):
        print("⏭️ sort_order уже существует")
    elif "no such table" in str(e):
        print("❌ Таблица domain_targets не существует — нужно сначала загрузить цели")
    else:
        print(f"⚠️ {e}")

# Добавляем item_type в license_targets
try:
    cursor.execute("ALTER TABLE license_targets ADD COLUMN item_type TEXT DEFAULT 'target'")
    print("✅ item_type добавлен")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e):
        print("⏭️ item_type уже существует")
    elif "no such table" in str(e):
        print("❌ Таблица license_targets не существует — нужно сначала вычислить цели")
    else:
        print(f"⚠️ {e}")

conn.commit()
conn.close()