import sqlite3
import os
import json
from datetime import datetime
from modules.logger import get_logger
import time

logger = get_logger(__name__)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
_DB_PATH = "local_licenses.db"

# ========== НАСТРОЙКА ПУТИ К БД ==========
def set_db_path(path):
    """Устанавливает путь к файлу БД"""
    global _DB_PATH
    _DB_PATH = path
    logger.info(f"Путь к БД установлен: {path}")

def get_db_path():
    """Возвращает текущий путь к файлу БД"""
    return _DB_PATH

# ========== ПОДКЛЮЧЕНИЕ К БД ==========
def get_connection(db_path=None):
    """Подключение к локальной БД с увеличенным таймаутом"""
    if db_path is None:
        db_path = _DB_PATH
    
    # Создаём директорию если нужно
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_local_db(db_path=None):
    """Инициализация локальной БД со всеми таблицами и индексами"""
    if db_path is None:
        db_path = _DB_PATH
    
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    # Таблица для иерархии SPart
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_spart_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            spart_name TEXT NOT NULL,
            spart_value INTEGER DEFAULT 0,
            spart_valid_date TEXT,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
        )
    ''')

    # Таблица для иерархии BPart
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_bpart_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            spart_id INTEGER,
            bpart_name TEXT NOT NULL,
            bpart_value INTEGER DEFAULT 0,
            bpart_valid_date TEXT,
            is_main BOOLEAN DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
            FOREIGN KEY (spart_id) REFERENCES license_spart_hierarchy(id) ON DELETE CASCADE
        )
    ''')

    # ========== ВОТ СЮДА ДОБАВЛЯЙТЕ ALTER TABLE ==========
    # Добавляем колонки для разделения PERMANENT и dated значений
    # (если они ещё не существуют)

    try:
        cursor.execute('ALTER TABLE license_spart_hierarchy ADD COLUMN permanent_value INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Колонка уже существует

    try:
        cursor.execute('ALTER TABLE license_spart_hierarchy ADD COLUMN dated_value INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE license_spart_hierarchy ADD COLUMN dated_date TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE license_bpart_hierarchy ADD COLUMN permanent_value INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE license_bpart_hierarchy ADD COLUMN dated_value INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE license_bpart_hierarchy ADD COLUMN dated_date TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE licenses ADD COLUMN local_path TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE licenses ADD COLUMN main_capacity_key TEXT')
    except sqlite3.OperationalError:
        pass

    # Таблица лицензий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            ne_type TEXT,
            city TEXT,
            site TEXT,
            year TEXT,
            filename TEXT,
            file_hash TEXT,
            lsn TEXT,
            product TEXT,
            version TEXT,
            esn TEXT,
            node TEXT,
            create_time TEXT,
            valid_date TEXT,
            last_modified TEXT,
            modified_by TEXT,
            domain TEXT,
            local_path TEXT,
            parsed_cache TEXT,
            UNIQUE(operator, ne_type, city, site, year, lsn)
        )
    ''')
    
    # Таблица ресурсов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER,
            capacity_key TEXT,
            value INTEGER,
            valid_date TEXT,
            FOREIGN KEY (license_id) REFERENCES licenses(id)
        )
    ''')
    
    # Таблица базовых целей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS base_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            ne_type TEXT,
            city TEXT,
            site TEXT,
            capacity_key TEXT,
            target_value INTEGER,
            updated_by TEXT,
            updated_at TEXT
        )
    ''')
    
    # Таблица доменных целей (из Excel Targets)
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
            sharing INTEGER DEFAULT 1,
            UNIQUE(operator, target_key, city)
        )
    ''')

    # Таблица формул (из Excel Formulas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ne_formulas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            domain TEXT,
            type TEXT,
            ne_type TEXT,
            capacity_key TEXT,
            formula TEXT,
            sharing INTEGER DEFAULT 1,
            main_key BOOLEAN DEFAULT 0,
            UNIQUE(operator, domain, type, ne_type, capacity_key)
        )
    ''')

    # Таблица вычисленных целей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            target_key TEXT,
            city TEXT,
            ne_type TEXT,
            capacity_key TEXT,
            target_value REAL,
            UNIQUE(operator, target_key, city, ne_type, capacity_key)
        )
    ''')
        
    # Таблица истории изменений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS change_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT,
            record_id INTEGER,
            action TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_at TEXT
        )
    ''')
    
    # Таблица маппинга ESN
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS esn_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            esn TEXT UNIQUE,
            lsn TEXT,
            operator TEXT,
            domain TEXT,
            ne_type TEXT,
            city TEXT,
            site TEXT
        )
    ''')
    
    # Таблица тегов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            color TEXT DEFAULT '#E60012',
            created_at TEXT
        )
    ''')
    
    # Таблица связи лицензий с тегами
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_tags (
            license_id INTEGER,
            tag_id INTEGER,
            FOREIGN KEY (license_id) REFERENCES licenses(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id),
            PRIMARY KEY (license_id, tag_id)
        )
    ''')
    
    # Таблица комментариев
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER,
            user_name TEXT,
            comment TEXT,
            created_at TEXT,
            FOREIGN KEY (license_id) REFERENCES licenses(id)
        )
    ''')
    
    # Таблица шаблонов отчётов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS report_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            filters TEXT,
            columns TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')
    
    # Таблица динамических колонок
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
    
    # Таблица значений динамических полей
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
    
    # ========== НОВАЯ ТАБЛИЦА ДЛЯ АГРЕГИРОВАННЫХ РЕСУРСОВ ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS capacity_aggregated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            capacity_key TEXT NOT NULL,
            total_value INTEGER DEFAULT 0,
            permanent_value INTEGER DEFAULT 0,
            dated_values TEXT,  -- JSON: [{"date": "2027-03-01", "value": 7215}, ...]
            latest_date TEXT,
            latest_value INTEGER,
            FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
            UNIQUE(license_id, capacity_key)
        )
    ''')
    
    # Таблица для иерархии SPart
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_spart_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            spart_name TEXT NOT NULL,
            spart_value INTEGER DEFAULT 0,
            spart_valid_date TEXT,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
        )
    ''')
    
    # Таблица для иерархии BPart (spart_id может быть NULL для "сирот")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_bpart_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            spart_id INTEGER,
            bpart_name TEXT NOT NULL,
            bpart_value INTEGER DEFAULT 0,
            bpart_valid_date TEXT,
            is_main BOOLEAN DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
            FOREIGN KEY (spart_id) REFERENCES license_spart_hierarchy(id) ON DELETE CASCADE
        )
    ''')
    
    # ========== ИНДЕКСЫ ДЛЯ УСКОРЕНИЯ ==========
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_licenses_operator_esn ON licenses(operator, esn)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_licenses_valid_date ON licenses(valid_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_licenses_esn_valid ON licenses(esn, valid_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_licenses_operator_ne_type ON licenses(operator, ne_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_licenses_lsn ON licenses(lsn)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_resources_license_id ON resources(license_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_resources_capacity_key ON resources(capacity_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dynamic_values_license_id ON dynamic_values(license_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_license_id ON comments(license_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_license_tags_license_id ON license_tags(license_id)')
    
    # Уникальный индекс с domain
    cursor.execute("DROP INDEX IF EXISTS idx_licenses_unique")
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_unique 
        ON licenses(operator, domain, ne_type, city, site, year, lsn)
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"Локальная БД инициализирована: {db_path}")
    
def add_change_history(table_name, record_id, action, old_value, new_value, changed_by):
    """Добавляет запись в историю изменений"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO change_history (table_name, record_id, action, old_value, new_value, changed_by, changed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (table_name, record_id, action, 
          json.dumps(old_value) if old_value else None,
          json.dumps(new_value) if new_value else None,
          changed_by, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_change_history(limit=100):
    """Получает историю изменений"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, table_name, record_id, action, old_value, new_value, changed_by, changed_at
        FROM change_history ORDER BY changed_at DESC LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        'id': r[0], 'table_name': r[1], 'record_id': r[2], 'action': r[3],
        'old_value': json.loads(r[4]) if r[4] else None,
        'new_value': json.loads(r[5]) if r[5] else None,
        'changed_by': r[6], 'changed_at': r[7]
    } for r in rows]
    
def save_licenses_batch(licenses_data, modified_by='system'):
    """
    Массовое сохранение лицензий в БД (одна транзакция)
    """
    if not licenses_data:
        return 0, 0

    conn = get_connection()
    cursor = conn.cursor()

    saved = 0
    errors = 0
    now = datetime.now().isoformat()

    try:
        for license_data in licenses_data:
            try:
                operator = license_data.get('operator')
                ne_type = license_data.get('ne_type')
                city = license_data.get('city')
                site = license_data.get('site')
                year = license_data.get('year')
                lsn = license_data.get('lsn')

                if not operator or not ne_type or not city:
                    errors += 1
                    continue

                # Проверяем существующую
                cursor.execute('''
                    SELECT id FROM licenses 
                    WHERE operator = ? AND ne_type = ? AND city = ? AND site = ? AND year = ? AND lsn = ?
                ''', (operator, ne_type, city, site, year, lsn))
                existing = cursor.fetchone()

                if existing:
                    license_id = existing[0]
                    cursor.execute('''
                        UPDATE licenses SET
                            filename=?, file_hash=?, product=?, version=?, esn=?, node=?,
                            create_time=?, valid_date=?, domain=?, local_path=?, parsed_cache=?,
                            last_modified=?, modified_by=?
                        WHERE id=?
                    ''', (
                        license_data.get('filename'), license_data.get('file_hash'),
                        license_data.get('product'), license_data.get('version'),
                        license_data.get('esn'), license_data.get('node'),
                        license_data.get('create_time'), license_data.get('valid_date'),
                        license_data.get('domain'), 
                        license_data.get('local_path', ''),
                        json.dumps(license_data.get('parsed_cache')) if license_data.get('parsed_cache') else None,
                        now, modified_by, license_id
                    ))
                else:
                    cursor.execute('''
                        INSERT INTO licenses (
                            operator, ne_type, city, site, year, filename, file_hash,
                            lsn, product, version, esn, node, create_time, valid_date,
                            domain, local_path, parsed_cache, last_modified, modified_by
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                operator, ne_type, city, site, year,
                                license_data.get('filename'), license_data.get('file_hash'),
                                lsn, license_data.get('product'), license_data.get('version'),
                                license_data.get('esn'), license_data.get('node'),
                                license_data.get('create_time'), license_data.get('valid_date'),
                                license_data.get('domain'),
                                license_data.get('local_path', ''),
                                json.dumps(license_data.get('parsed_cache')) if license_data.get('parsed_cache') else None,
                                now,  # last_modified
                                modified_by  # modified_by
                            ))
                    license_id = cursor.lastrowid

                # ========== СОХРАНЯЕМ ОБЫЧНЫЕ РЕСУРСЫ ==========
                for res in license_data.get('resources', []):
                    if isinstance(res, dict):
                        capacity_key = res.get('name') or res.get('capacity_key')
                        value = res.get('value', 0)
                        valid_date = res.get('valid_date', license_data.get('valid_date', 'UNKNOWN'))
                        if capacity_key:
                            cursor.execute('''
                                INSERT INTO resources (license_id, capacity_key, value, valid_date)
                                VALUES (?, ?, ?, ?)
                            ''', (license_id, capacity_key, value, valid_date))
                
                # ========== СОХРАНЯЕМ ИЕРАРХИЮ SPart/BPart ==========
                # Удаляем старые иерархические данные
                cursor.execute('DELETE FROM license_bpart_hierarchy WHERE license_id = ?', (license_id,))
                cursor.execute('DELETE FROM license_spart_hierarchy WHERE license_id = ?', (license_id,))
                
                # Получаем иерархию из parsed_cache или license_data
                hierarchy = None
                if 'spart_hierarchy' in license_data:
                    hierarchy = license_data['spart_hierarchy']
                elif license_data.get('parsed_cache'):
                    hierarchy = license_data['parsed_cache'].get('spart_hierarchy')
                
                if hierarchy:
                    # Сортируем SPart по порядку (если есть sort_order)
                    sparts_list = hierarchy.get('sparts', [])
                    
                    for spart in sparts_list:
                        cursor.execute('''
                            INSERT INTO license_spart_hierarchy 
                            (license_id, spart_name, spart_value, spart_valid_date, 
                            permanent_value, dated_value, dated_date, sort_order)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (license_id, spart.get('name'), spart.get('value', 0), 
                            spart.get('valid_date', 'UNKNOWN'),
                            spart.get('permanent_value', 0),
                            spart.get('dated_value', 0),
                            spart.get('dated_date'),
                            spart.get('sort_order', 0)))
                        spart_id = cursor.lastrowid  # <-- Эта строка ОБЯЗАТЕЛЬНА

                        for bpart in spart.get('bparts', []):
                            is_main = 1 if bpart.get('is_main') else 0
                            cursor.execute('''
                                INSERT INTO license_bpart_hierarchy 
                                (license_id, spart_id, bpart_name, bpart_value, bpart_valid_date,
                                permanent_value, dated_value, dated_date, is_main, sort_order)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (license_id, spart_id, bpart.get('name'), bpart.get('value', 0), 
                                bpart.get('valid_date', 'UNKNOWN'),
                                bpart.get('permanent_value', 0),
                                bpart.get('dated_value', 0),
                                bpart.get('dated_date'),
                                is_main, bpart.get('sort_order', 0)))
                       
                    # Сохраняем "сирот" (bpart без родительского spart) — теперь spart_id может быть NULL
                    for orphan in hierarchy.get('orphan_bparts', []):
                        cursor.execute('''
                            INSERT INTO license_bpart_hierarchy 
                            (license_id, spart_id, bpart_name, bpart_value, bpart_valid_date,
                            permanent_value, dated_value, dated_date, is_main, sort_order)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (license_id, None, orphan.get('name'), orphan.get('value', 0), 
                            orphan.get('valid_date', 'UNKNOWN'),
                            orphan.get('permanent_value', 0),
                            orphan.get('dated_value', 0),
                            orphan.get('dated_date'),
                            0, orphan.get('sort_order', 0)))
    
                # ========== НОВОЕ: СОХРАНЯЕМ АГРЕГИРОВАННЫЕ ДАННЫЕ ==========
                # Проверяем, есть ли в license_data агрегированные ресурсы
                if 'aggregated_resources' in license_data:
                    for agg_res in license_data['aggregated_resources']:
                        cursor.execute('''
                            INSERT OR REPLACE INTO capacity_aggregated 
                            (license_id, capacity_key, total_value, permanent_value, dated_values, latest_date, latest_value)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            license_id, 
                            agg_res.get('name'),
                            agg_res.get('total_value', 0),
                            agg_res.get('permanent_value', 0),
                            agg_res.get('dated_values', '[]'),
                            agg_res.get('latest_date'),
                            agg_res.get('latest_value', 0)
                        ))
                else:
                    # Если агрегированных данных нет, создаём их из обычных ресурсов
                    # Группируем ресурсы по capacity_key
                    agg_dict = {}
                    for res in license_data.get('resources', []):
                        key = res.get('name')
                        if not key:
                            continue
                        if key not in agg_dict:
                            agg_dict[key] = {
                                'name': key,
                                'total_value': 0,
                                'permanent_value': 0,
                                'dated_values': [],
                                'latest_date': None,
                                'latest_value': 0
                            }
                        entry = agg_dict[key]
                        value = res.get('value', 0)
                        valid_date = res.get('valid_date', 'UNKNOWN')
                        
                        entry['total_value'] += value
                        if valid_date == 'PERMANENT':
                            entry['permanent_value'] += value
                        elif valid_date not in ['UNKNOWN', '']:
                            entry['dated_values'].append({'date': valid_date, 'value': value})
                            if entry['latest_date'] is None or valid_date > entry['latest_date']:
                                entry['latest_date'] = valid_date
                                entry['latest_value'] = value
                    
                    # Сохраняем агрегированные данные
                    for key, data in agg_dict.items():
                        cursor.execute('''
                            INSERT OR REPLACE INTO capacity_aggregated 
                            (license_id, capacity_key, total_value, permanent_value, dated_values, latest_date, latest_value)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            license_id,
                            data['name'],
                            data['total_value'],
                            data['permanent_value'],
                            json.dumps(data['dated_values']),
                            data['latest_date'],
                            data['latest_value']
                        ))

                saved += 1

            except Exception as e:
                errors += 1
                logger.error(f"Ошибка сохранения лицензии в пакете: {e}")

        conn.commit()
        return saved, errors

    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка пакетного сохранения: {e}")
        return saved, errors
    finally:
        conn.close()
        
def save_license(license_data, modified_by='system', max_retries=5):
    """
    Сохраняет лицензию в БД с повторными попытками при блокировке
    
    Args:
        license_data: dict с данными лицензии
        modified_by: str - кто изменяет
        max_retries: int - максимальное количество попыток
    
    Returns:
        int - ID лицензии
    """
    for attempt in range(max_retries):
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Подготовка данных
            operator = license_data.get('operator')
            ne_type = license_data.get('ne_type')
            city = license_data.get('city')
            site = license_data.get('site')
            year = license_data.get('year')
            lsn = license_data.get('lsn')
            
            # Проверяем обязательные поля
            if not operator:
                raise ValueError("operator обязателен")
            if not ne_type:
                raise ValueError("ne_type обязателен")
            if not city:
                raise ValueError("city обязателен")
            
            # Проверяем существующую лицензию
            cursor.execute('''
                SELECT id FROM licenses 
                WHERE operator = ? AND ne_type = ? AND city = ? AND site = ? AND year = ? AND lsn = ?
            ''', (operator, ne_type, city, site, year, lsn))
            existing = cursor.fetchone()
            
            now = datetime.now().isoformat()
            
            # Общие поля для INSERT и UPDATE
            common_fields = {
                'filename': license_data.get('filename'),
                'file_hash': license_data.get('file_hash'),
                'product': license_data.get('product'),
                'version': license_data.get('version'),
                'esn': license_data.get('esn'),
                'node': license_data.get('node'),
                'create_time': license_data.get('create_time'),
                'valid_date': license_data.get('valid_date'),
                'domain': license_data.get('domain'),
                'parsed_cache': json.dumps(license_data.get('parsed_cache')) if license_data.get('parsed_cache') else None,
                'last_modified': now,
                'modified_by': modified_by
            }
            
            if existing:
                # ОБНОВЛЕНИЕ существующей лицензии
                license_id = existing[0]
                
                # Проверяем, нужно ли обновлять ресурсы
                # (если ресурсы не переданы, возможно, их не нужно трогать)
                if 'resources' in license_data and license_data['resources']:
                    # Удаляем старые ресурсы
                    cursor.execute('DELETE FROM resources WHERE license_id = ?', (license_id,))
                
                # Обновляем лицензию
                cursor.execute('''
                    UPDATE licenses SET
                        filename = ?,
                        file_hash = ?,
                        product = ?,
                        version = ?,
                        esn = ?,
                        node = ?,
                        create_time = ?,
                        valid_date = ?,
                        domain = ?,
                        parsed_cache = ?,
                        last_modified = ?,
                        modified_by = ?
                    WHERE id = ?
                ''', (
                    common_fields['filename'],
                    common_fields['file_hash'],
                    common_fields['product'],
                    common_fields['version'],
                    common_fields['esn'],
                    common_fields['node'],
                    common_fields['create_time'],
                    common_fields['valid_date'],
                    common_fields['domain'],
                    common_fields['parsed_cache'],
                    common_fields['last_modified'],
                    common_fields['modified_by'],
                    license_id
                ))
                
                # Логируем изменение
                add_change_history('licenses', license_id, 'UPDATE', 
                                  {'old_data': 'updated'}, 
                                  {'new_data': license_data.get('lsn')}, 
                                  modified_by)
                
            else:
                # ВСТАВКА новой лицензии
                cursor.execute('''
                    INSERT INTO licenses (
                        operator, ne_type, city, site, year, filename, file_hash,
                        lsn, product, version, esn, node, create_time, valid_date,
                        domain, parsed_cache, last_modified, modified_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    operator,
                    ne_type,
                    city,
                    site,
                    year,
                    common_fields['filename'],
                    common_fields['file_hash'],
                    lsn,
                    common_fields['product'],
                    common_fields['version'],
                    common_fields['esn'],
                    common_fields['node'],
                    common_fields['create_time'],
                    common_fields['valid_date'],
                    common_fields['domain'],
                    common_fields['parsed_cache'],
                    common_fields['last_modified'],
                    common_fields['modified_by']
                ))
                license_id = cursor.lastrowid
                
                # Логируем создание
                add_change_history('licenses', license_id, 'INSERT', 
                                  None, 
                                  {'lsn': lsn, 'operator': operator}, 
                                  modified_by)
            
            # Сохраняем ресурсы (если есть)
            resources = license_data.get('resources', [])
            if resources:
                for res in resources:
                    # Проверяем, что ресурс имеет нужные поля
                    if isinstance(res, dict):
                        capacity_key = res.get('name') or res.get('capacity_key')
                        value = res.get('value', 0)
                        valid_date = res.get('valid_date', license_data.get('valid_date', 'UNKNOWN'))
                        
                        if capacity_key:
                            cursor.execute('''
                                INSERT INTO resources (license_id, capacity_key, value, valid_date)
                                VALUES (?, ?, ?, ?)
                            ''', (license_id, capacity_key, value, valid_date))
            
            # Сохраняем динамические значения (если есть)
            dynamic_values = license_data.get('dynamic_values', {})
            if dynamic_values:
                for column_name, value in dynamic_values.items():
                    # Находим column_id по имени
                    cursor.execute('SELECT id FROM dynamic_columns WHERE column_name = ?', (column_name,))
                    col_row = cursor.fetchone()
                    if col_row:
                        column_id = col_row[0]
                        cursor.execute('''
                            INSERT OR REPLACE INTO dynamic_values (license_id, column_id, value)
                            VALUES (?, ?, ?)
                        ''', (license_id, column_id, str(value) if value else None))
            
            conn.commit()
            conn.close()
            return license_id
            
        except Exception as e:
            if conn:
                conn.close()
            
            error_msg = str(e).lower()
            if "locked" in error_msg or "busy" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = 0.1 * (attempt + 1)
                    logger.warning(f"БД заблокирована, повторная попытка {attempt + 1}/{max_retries} через {wait_time:.2f} сек...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Не удалось сохранить лицензию после {max_retries} попыток: {e}")
                    raise
            else:
                logger.error(f"Ошибка сохранения лицензии: {e}")
                raise
        
                  
def get_all_licenses(operator=None, ne_type=None, city=None):
    """Получает список лицензий с фильтрацией"""
    conn = get_connection()
    cursor = conn.cursor()

    query = '''SELECT id, operator, ne_type, city, site, year, lsn, product, version, 
               create_time, valid_date, filename, file_hash, domain, local_path, esn, node
               FROM licenses WHERE 1=1'''
    params = []

    if operator and operator != 'all':
        query += ' AND operator = ?'
        params.append(operator)
    if ne_type and ne_type != 'all':
        query += ' AND ne_type = ?'
        params.append(ne_type)
    if city and city != 'all':
        query += ' AND city = ?'
        params.append(city)

    query += ' ORDER BY operator, ne_type, city, year DESC'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [{
        'id': r[0], 'operator': r[1], 'ne_type': r[2], 'city': r[3], 
        'site': r[4], 'year': r[5] or 'бессрочная', 'lsn': r[6], 
        'product': r[7], 'version': r[8], 'create_time': r[9], 'valid_date': r[10],
        'filename': r[11], 'file_hash': r[12], 'domain': r[13], 'local_path': r[14],
        'esn': r[15], 'node': r[16]
    } for r in rows]
    
def get_license_by_id(license_id):
    """Получает лицензию по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM licenses WHERE id = ?', (license_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    # Получаем имена колонок
    columns = [desc[0] for desc in cursor.description]
    license_dict = dict(zip(columns, row))
    
    cursor.execute('SELECT capacity_key, value, valid_date FROM resources WHERE license_id = ?', (license_id,))
    resources = cursor.fetchall()
    conn.close()
    
    license_dict['resources'] = [{'name': r[0], 'value': r[1], 'valid_date': r[2]} for r in resources]
    
    return license_dict
  
def get_unique_esn_licenses(operator):
    """
    Возвращает уникальные ESN с самой актуальной лицензией
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Более простой и быстрый запрос
    cursor.execute('''
        SELECT 
            l1.id,
            l1.operator,
            l1.ne_type,
            l1.city,
            l1.site,
            l1.year,
            l1.lsn,
            l1.product,
            l1.version,
            l1.esn,
            l1.node,
            l1.create_time,
            l1.valid_date,
            l1.filename,
            l1.domain
        FROM licenses l1
        WHERE l1.operator = ? 
        AND l1.esn IS NOT NULL 
        AND l1.esn != ''
        AND l1.id = (
            SELECT l2.id FROM licenses l2
            WHERE l2.esn = l1.esn
            AND l2.operator = l1.operator
            ORDER BY 
                CASE 
                    WHEN l2.valid_date != 'PERMANENT' AND l2.valid_date != 'UNKNOWN' THEN l2.valid_date 
                    ELSE '0000-00-00'
                END DESC,
                l2.create_time DESC
            LIMIT 1
        )
        ORDER BY l1.ne_type, l1.city, l1.esn
    ''', (operator,))
    
    rows = cursor.fetchall()
    conn.close()
    
    licenses = []
    for row in rows:
        licenses.append({
            'id': row[0],
            'operator': row[1],
            'ne_type': row[2],
            'city': row[3],
            'site': row[4],
            'year': row[5],
            'lsn': row[6],
            'product': row[7],
            'version': row[8],
            'esn': row[9],
            'node': row[10],
            'create_time': row[11],
            'valid_date': row[12],
            'filename': row[13],
            'domain': row[14]
        })
    
    return licenses

def get_all_licenses_for_esn(operator, esn):
    """Получает все лицензии для конкретного ESN (с ресурсами из parsed_cache)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, lsn, filename, product, version, create_time, valid_date, year, parsed_cache
        FROM licenses
        WHERE operator = ? AND esn = ?
        ORDER BY 
            CASE 
                WHEN valid_date != 'PERMANENT' AND valid_date != 'UNKNOWN' THEN valid_date 
                ELSE '0000-00-00'
            END DESC,
            create_time DESC
    ''', (operator, esn))
    rows = cursor.fetchall()
    conn.close()
    
    licenses = []
    for row in rows:
        lic = {
            'id': row[0],
            'lsn': row[1],
            'filename': row[2],
            'product': row[3],
            'version': row[4],
            'create_time': row[5],
            'valid_date': row[6],
            'year': row[7]
        }
        
        # Извлекаем ресурсы из parsed_cache
        if len(row) > 8 and row[8]:
            try:
                import json
                parsed_cache = json.loads(row[8]) if isinstance(row[8], str) else row[8]
                lic['resources'] = parsed_cache.get('resources', [])
            except:
                lic['resources'] = []
        else:
            lic['resources'] = []
        
        licenses.append(lic)
    
    return licenses
def save_base_target(operator, ne_type, city, site, capacity_key, target_value, updated_by):
    """Сохраняет базовую цель"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id FROM base_targets 
        WHERE operator = ? AND ne_type = ? AND city = ? AND site = ? AND capacity_key = ?
    ''', (operator, ne_type, city, site, capacity_key))
    existing = cursor.fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        cursor.execute('''
            UPDATE base_targets SET target_value = ?, updated_by = ?, updated_at = ?
            WHERE id = ?
        ''', (target_value, updated_by, now, existing[0]))
        add_change_history('base_targets', existing[0], 'UPDATE', None, 
                          {'target_value': target_value}, updated_by)
    else:
        cursor.execute('''
            INSERT INTO base_targets (operator, ne_type, city, site, capacity_key, target_value, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (operator, ne_type, city, site, capacity_key, target_value, updated_by, now))
        add_change_history('base_targets', cursor.lastrowid, 'INSERT', None,
                          {'target_value': target_value}, updated_by)
    
    conn.commit()
    conn.close()

def get_base_targets(operator, ne_type, city, site):
    """Получает базовые цели"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT capacity_key, target_value FROM base_targets
        WHERE operator = ? AND ne_type = ? AND city = ? AND site = ?
    ''', (operator, ne_type, city, site))
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

# ========== ТЕГИ ==========

def add_tag(name, color='#E60012'):
    """Добавляет новый тег"""
    from datetime import datetime
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO tags (name, color, created_at) VALUES (?, ?, ?)',
                   (name, color, datetime.now().isoformat()))
    conn.commit()
    cursor.execute('SELECT id FROM tags WHERE name = ?', (name,))
    tag_id = cursor.fetchone()[0] if cursor.rowcount > 0 else None
    conn.close()
    return tag_id

def get_all_tags():
    """Возвращает все теги"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, color FROM tags ORDER BY name')
    tags = [{'id': r[0], 'name': r[1], 'color': r[2]} for r in cursor.fetchall()]
    conn.close()
    return tags

def add_tag_to_license(license_id, tag_id):
    """Добавляет тег лицензии"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO license_tags (license_id, tag_id) VALUES (?, ?)',
                   (license_id, tag_id))
    conn.commit()
    conn.close()

def remove_tag_from_license(license_id, tag_id):
    """Удаляет тег с лицензии"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM license_tags WHERE license_id = ? AND tag_id = ?',
                   (license_id, tag_id))
    conn.commit()
    conn.close()

def get_license_tags(license_id):
    """Возвращает теги лицензии"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.id, t.name, t.color 
        FROM tags t
        JOIN license_tags lt ON lt.tag_id = t.id
        WHERE lt.license_id = ?
    ''', (license_id,))
    tags = [{'id': r[0], 'name': r[1], 'color': r[2]} for r in cursor.fetchall()]
    conn.close()
    return tags

# ========== КОММЕНТАРИИ ==========

def add_comment(license_id, user_name, comment):
    """Добавляет комментарий к лицензии"""
    from datetime import datetime
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO comments (license_id, user_name, comment, created_at)
        VALUES (?, ?, ?, ?)
    ''', (license_id, user_name, comment, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_comments(license_id):
    """Возвращает комментарии лицензии"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_name, comment, created_at 
        FROM comments 
        WHERE license_id = ?
        ORDER BY created_at DESC
    ''', (license_id,))
    comments = [{'id': r[0], 'user_name': r[1], 'comment': r[2], 'created_at': r[3]} 
                for r in cursor.fetchall()]
    conn.close()
    return comments

# ========== ШАБЛОНЫ ОТЧЁТОВ ==========

def save_report_template(name, description, filters, columns, created_by):
    """Сохраняет шаблон отчёта"""
    import json
    from datetime import datetime
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO report_templates (name, description, filters, columns, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, description, json.dumps(filters), json.dumps(columns), 
          created_by, datetime.now().isoformat()))
    conn.commit()
    template_id = cursor.lastrowid
    conn.close()
    return template_id

def get_report_templates():
    """Возвращает все шаблоны отчётов"""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, filters, columns, created_by, created_at FROM report_templates')
    templates = []
    for r in cursor.fetchall():
        templates.append({
            'id': r[0], 'name': r[1], 'description': r[2],
            'filters': json.loads(r[3]), 'columns': json.loads(r[4]),
            'created_by': r[5], 'created_at': r[6]
        })
    conn.close()
    return templates

# Добавьте эти функции в конец файла modules/database.py

def get_filter_options(operator):
    """Получает уникальные значения для фильтров"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT ne_type FROM licenses WHERE ne_type IS NOT NULL AND ne_type != ""')
    ne_types = [r[0] for r in cursor.fetchall()]
    
    cursor.execute('SELECT DISTINCT city FROM licenses WHERE city IS NOT NULL AND city != ""')
    cities = [r[0] for r in cursor.fetchall()]
    
    cursor.execute('SELECT DISTINCT year FROM licenses WHERE year IS NOT NULL AND year != "" ORDER BY year DESC')
    years = [r[0] for r in cursor.fetchall()]
    
    conn.close()
    return {'ne_types': ne_types, 'cities': cities, 'years': years}

def get_db_path(operator=None):
    """Возвращает путь к БД"""
    if operator and operator != 'test':
        return f'operators/{operator}/licenses.db'
    return 'local_licenses.db'

def backup_database(operator):
    """Создаёт резервную копию БД оператора"""
    import shutil
    from datetime import datetime
    
    db_path = get_db_path(operator) if operator != 'test' else 'local_licenses.db'
    if not os.path.exists(db_path):
        return None
    
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'licenses_backup_{timestamp}.db')
    shutil.copy2(db_path, backup_path)
    
    return backup_path


def delete_report_template(template_id):
    """Удаляет шаблон отчёта"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM report_templates WHERE id = ?', (template_id,))
    conn.commit()
    conn.close()
    
# Добавьте эти функции в конец файла modules/database.py

# ========== ДИНАМИЧЕСКИЕ ПОЛЯ ==========

def get_dynamic_columns(active_only=True):
    """Получить все динамические колонки"""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT id, column_name, display_name, rule_id, capacity_key, aggregation_strategy, join_separator, is_active, created_at, updated_at FROM dynamic_columns"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        'id': r[0],
        'column_name': r[1],
        'display_name': r[2],
        'rule_id': r[3],
        'capacity_key': r[4],
        'aggregation_strategy': r[5],
        'join_separator': r[6],
        'is_active': r[7],
        'created_at': r[8],
        'updated_at': r[9]
    } for r in rows]


def add_dynamic_column(column_name, display_name, rule_id=None, capacity_key=None, 
                       aggregation_strategy='sum', join_separator=', '):
    """Добавить динамическую колонку"""
    from datetime import datetime
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO dynamic_columns 
            (column_name, display_name, rule_id, capacity_key, aggregation_strategy, join_separator, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (column_name, display_name, rule_id, capacity_key, aggregation_strategy, join_separator,
              datetime.now().isoformat(), datetime.now().isoformat()))
        column_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return column_id
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Колонка с именем '{column_name}' уже существует")


def update_dynamic_column(column_id, **kwargs):
    """Обновить динамическую колонку"""
    from datetime import datetime
    
    allowed_fields = ['display_name', 'aggregation_strategy', 'join_separator', 'is_active']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if not updates:
        return
    
    updates['updated_at'] = datetime.now().isoformat()
    
    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [column_id]
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE dynamic_columns SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_dynamic_column(column_id):
    """Удалить динамическую колонку (и все связанные значения)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dynamic_values WHERE column_id = ?", (column_id,))
    cursor.execute("DELETE FROM dynamic_columns WHERE id = ?", (column_id,))
    conn.commit()
    conn.close()


def set_dynamic_value(license_id, column_id, value):
    """Установить значение динамического поля для лицензии"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO dynamic_values (license_id, column_id, value)
        VALUES (?, ?, ?)
    ''', (license_id, column_id, str(value) if value is not None else None))
    
    conn.commit()
    conn.close()


def get_dynamic_values_for_license(license_id):
    """Получить все динамические значения для лицензии"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT dc.column_name, dc.display_name, dv.value, dc.aggregation_strategy
        FROM dynamic_values dv
        JOIN dynamic_columns dc ON dv.column_id = dc.id
        WHERE dv.license_id = ?
    ''', (license_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {r[0]: {'value': r[2], 'display_name': r[1], 'strategy': r[3]} for r in rows}


def get_all_dynamic_values_for_list(license_ids):
    """
    Получить динамические значения для списка лицензий (для таблицы)
    Возвращает словарь {license_id: {column_name: value}}
    """
    if not license_ids:
        return {}
    
    placeholders = ','.join('?' * len(license_ids))
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(f'''
        SELECT dv.license_id, dc.column_name, dv.value
        FROM dynamic_values dv
        JOIN dynamic_columns dc ON dv.column_id = dc.id
        WHERE dv.license_id IN ({placeholders}) AND dc.is_active = 1
    ''', license_ids)
    
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for lic_id, col_name, value in rows:
        if lic_id not in result:
            result[lic_id] = {}
        result[lic_id][col_name] = value
    
    return result


# ========== АГРЕГИРОВАННЫЕ ТЕГИ И КОММЕНТАРИИ ==========

def get_licenses_with_tags_and_comments(licenses):
    """
    Дополняет список лицензий агрегированными тегами и количеством комментариев
    """
    if not licenses:
        return licenses
    
    license_ids = [l['id'] for l in licenses]
    placeholders = ','.join('?' * len(license_ids))
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем теги для всех лицензий
    cursor.execute(f'''
        SELECT lt.license_id, GROUP_CONCAT(DISTINCT t.name) as tags
        FROM license_tags lt
        JOIN tags t ON lt.tag_id = t.id
        WHERE lt.license_id IN ({placeholders})
        GROUP BY lt.license_id
    ''', license_ids)
    tags_rows = cursor.fetchall()
    tags_map = {r[0]: r[1] for r in tags_rows}
    
    # Получаем количество комментариев
    cursor.execute(f'''
        SELECT license_id, COUNT(*) as comments_count
        FROM comments
        WHERE license_id IN ({placeholders})
        GROUP BY license_id
    ''', license_ids)
    comments_rows = cursor.fetchall()
    comments_map = {r[0]: r[1] for r in comments_rows}
    
    conn.close()
    
    # Обогащаем лицензии
    for lic in licenses:
        lic['tags_agg'] = tags_map.get(lic['id'], '')
        lic['comments_count'] = comments_map.get(lic['id'], 0)
    
    return licenses


# ========== ДЛЯ ЭКСПОРТА ==========

def get_all_licenses_for_export(operator, license_ids=None):
    """
    Получает все данные для экспорта (с динамическими полями, тегами, комментариями)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if license_ids:
        placeholders = ','.join('?' * len(license_ids))
        query = f'''
            SELECT id, operator, ne_type, city, site, year, lsn, product, version, esn, create_time, valid_date, domain
            FROM licenses 
            WHERE operator = ? AND id IN ({placeholders})
            ORDER BY ne_type, city
        '''
        params = [operator] + license_ids
    else:
        query = '''
            SELECT id, operator, ne_type, city, site, year, lsn, product, version, esn, create_time, valid_date, domain
            FROM licenses 
            WHERE operator = ?
            ORDER BY ne_type, city
        '''
        params = [operator]
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    licenses = [{ 
        'id': r[0], 'operator': r[1], 'ne_type': r[2], 'city': r[3],
        'site': r[4], 'year': r[5], 'lsn': r[6], 'product': r[7],
        'version': r[8], 'esn': r[9], 'create_time': r[10], 
        'valid_date': r[11], 'domain': r[12]
    } for r in rows]
    
    # Добавляем теги, комментарии и динамические поля
    licenses = get_licenses_with_tags_and_comments(licenses)
    
    lic_ids = [l['id'] for l in licenses]
    dynamic_values = get_all_dynamic_values_for_list(lic_ids)
    
    for lic in licenses:
        if lic['id'] in dynamic_values:
            lic['dynamic_values'] = dynamic_values[lic['id']]
        else:
            lic['dynamic_values'] = {}
    
    return licenses

# ========== ОБНОВЛЕНИЕ КЭША ==========

def update_parsed_cache(license_id, parsed_cache):
    """
    Обновляет parsed_cache для лицензии
    
    Args:
        license_id: int - ID лицензии
        parsed_cache: dict - данные кэша парсинга
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE licenses SET parsed_cache = ? WHERE id = ?
        ''', (json.dumps(parsed_cache, ensure_ascii=False) if parsed_cache else None, license_id))
        
        conn.commit()
        logger.debug(f"Обновлён parsed_cache для лицензии {license_id}")
    except Exception as e:
        logger.error(f"Ошибка обновления parsed_cache для лицензии {license_id}: {e}")
        raise
    finally:
        conn.close()


def get_parsed_cache(license_id):
    """
    Получает parsed_cache для лицензии
    
    Args:
        license_id: int - ID лицензии
    
    Returns:
        dict - данные кэша или None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT parsed_cache FROM licenses WHERE id = ?', (license_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        return json.loads(row[0])
    return None

# ========== АГРЕГИРОВАННЫЕ ДАННЫЕ ДЛЯ ЛИЦЕНЗИЙ ==========

def get_license_aggregated_data(license_id):
    """
    Получает агрегированные данные для лицензии (теги, комментарии, динамические поля)
    
    Args:
        license_id: int - ID лицензии
    
    Returns:
        dict - с ключами 'tags', 'comments_count', 'dynamic_values'
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    result = {
        'tags': [],
        'comments_count': 0,
        'dynamic_values': {}
    }
    
    # Получаем теги
    cursor.execute('''
        SELECT t.id, t.name, t.color 
        FROM tags t
        JOIN license_tags lt ON lt.tag_id = t.id
        WHERE lt.license_id = ?
    ''', (license_id,))
    result['tags'] = [{'id': r[0], 'name': r[1], 'color': r[2]} for r in cursor.fetchall()]
    
    # Получаем количество комментариев
    cursor.execute('SELECT COUNT(*) FROM comments WHERE license_id = ?', (license_id,))
    result['comments_count'] = cursor.fetchone()[0]
    
    # Получаем динамические значения
    cursor.execute('''
        SELECT dc.column_name, dc.display_name, dv.value
        FROM dynamic_values dv
        JOIN dynamic_columns dc ON dv.column_id = dc.id
        WHERE dv.license_id = ? AND dc.is_active = 1
    ''', (license_id,))
    
    for row in cursor.fetchall():
        result['dynamic_values'][row[0]] = {
            'display_name': row[1],
            'value': row[2]
        }
    
    conn.close()
    return result


def get_licenses_aggregated_data_batch(license_ids):
    """
    Получает агрегированные данные для нескольких лицензий (для списка)
    
    Args:
        license_ids: list[int] - список ID лицензий
    
    Returns:
        dict - {license_id: {'tags': str, 'comments_count': int}}
    """
    if not license_ids:
        return {}
    
    placeholders = ','.join('?' * len(license_ids))
    conn = get_connection()
    cursor = conn.cursor()
    
    result = {lid: {'tags_agg': '', 'comments_count': 0} for lid in license_ids}
    
    # Получаем теги (агрегированные в строку)
    cursor.execute(f'''
        SELECT lt.license_id, GROUP_CONCAT(DISTINCT t.name, ', ') as tags
        FROM license_tags lt
        JOIN tags t ON lt.tag_id = t.id
        WHERE lt.license_id IN ({placeholders})
        GROUP BY lt.license_id
    ''', license_ids)
    
    for row in cursor.fetchall():
        result[row[0]]['tags_agg'] = row[1] or ''
    
    # Получаем количество комментариев
    cursor.execute(f'''
        SELECT license_id, COUNT(*) as cnt
        FROM comments
        WHERE license_id IN ({placeholders})
        GROUP BY license_id
    ''', license_ids)
    
    for row in cursor.fetchall():
        result[row[0]]['comments_count'] = row[1]
    
    conn.close()
    return result


def update_license_aggregated_cache(license_id):
    """
    Обновляет кэш агрегированных данных (для оптимизации)
    
    Args:
        license_id: int - ID лицензии
    """
    data = get_license_aggregated_data(license_id)
    
    # Обновляем поле tags_agg в licenses (если добавим)
    # Пока оставим заглушку
    pass


def search_licenses_by_text(operator, search_text, limit=100):
    """
    Поиск лицензий по тексту в разных полях
    
    Args:
        operator: str - оператор
        search_text: str - текст для поиска
        limit: int - максимум результатов
    
    Returns:
        list - найденные лицензии
    """
    if not search_text:
        return []
    
    search_pattern = f'%{search_text}%'
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, operator, ne_type, city, site, year, lsn, product, version, esn, domain
        FROM licenses
        WHERE operator = ?
        AND (
            lsn LIKE ? OR
            product LIKE ? OR
            version LIKE ? OR
            esn LIKE ? OR
            ne_type LIKE ? OR
            city LIKE ? OR
            site LIKE ? OR
            domain LIKE ?
        )
        LIMIT ?
    ''', (operator, search_pattern, search_pattern, search_pattern, 
          search_pattern, search_pattern, search_pattern, search_pattern, 
          search_pattern, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        'id': r[0],
        'operator': r[1],
        'ne_type': r[2],
        'city': r[3],
        'site': r[4],
        'year': r[5],
        'lsn': r[6],
        'product': r[7],
        'version': r[8],
        'esn': r[9],
        'domain': r[10]
    } for r in rows]
    
# ========== ПОЛУЧЕНИЕ ЛИЦЕНЗИЙ С АГРЕГИРОВАННЫМИ ДАННЫМИ ==========

def get_all_licenses_with_aggregated(operator=None, ne_type=None, city=None, limit=None, offset=None):
    """
    Получает список лицензий с агрегированными тегами и комментариями
    
    Args:
        operator: str - фильтр по оператору
        ne_type: str - фильтр по NE типу
        city: str - фильтр по городу
        limit: int - лимит записей
        offset: int - смещение для пагинации
    
    Returns:
        list - лицензии с полями tags_agg и comments_count
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT 
            l.id, l.operator, l.ne_type, l.city, l.site, l.year, 
            l.lsn, l.product, l.version, l.esn, l.create_time, l.valid_date, l.domain,
            COALESCE(g.tags, '') as tags_agg,
            COALESCE(c.cnt, 0) as comments_count
        FROM licenses l
        LEFT JOIN (
            SELECT lt.license_id, GROUP_CONCAT(DISTINCT t.name, ', ') as tags
            FROM license_tags lt
            JOIN tags t ON lt.tag_id = t.id
            GROUP BY lt.license_id
        ) g ON l.id = g.license_id
        LEFT JOIN (
            SELECT license_id, COUNT(*) as cnt
            FROM comments
            GROUP BY license_id
        ) c ON l.id = c.license_id
        WHERE 1=1
    '''
    params = []
    
    if operator and operator != 'all':
        query += ' AND l.operator = ?'
        params.append(operator)
    if ne_type and ne_type != 'all':
        query += ' AND l.ne_type = ?'
        params.append(ne_type)
    if city and city != 'all':
        query += ' AND l.city = ?'
        params.append(city)
    
    query += ' ORDER BY l.operator, l.ne_type, l.city, l.year DESC'
    
    if limit:
        query += ' LIMIT ?'
        params.append(limit)
    if offset:
        query += ' OFFSET ?'
        params.append(offset)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        'id': r[0],
        'operator': r[1],
        'ne_type': r[2],
        'city': r[3],
        'site': r[4],
        'year': r[5] or 'бессрочная',
        'lsn': r[6],
        'product': r[7],
        'version': r[8],
        'esn': r[9],
        'create_time': r[10],
        'valid_date': r[11],
        'domain': r[12],
        'tags_agg': r[13],
        'comments_count': r[14]
    } for r in rows]
    
# ========== УПРАВЛЕНИЕ СОЕДИНЕНИЯМИ ==========

def close_all_connections():
    """
    Принудительно закрывает все соединения с БД
    Вызывать перед операциями, которые могут вызвать блокировку
    """
    import gc
    gc.collect()  # Сборка мусора для закрытия неиспользуемых соединений
    
    # Принудительное закрытие через sqlite3
    try:
        # Создаём временное соединение, чтобы завершить все ожидающие транзакции
        conn = sqlite3.connect(_DB_PATH, timeout=1.0)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception as e:
        logger.debug(f"Очистка соединений: {e}")


def force_release_db():
    """
    Полное освобождение БД - закрывает все соединения и выполняет checkpoint
    """
    import gc
    
    # Сборка мусора
    gc.collect()
    
    # Принудительный checkpoint для WAL режима
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=1.0)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception:
        pass
    
    # Дополнительная очистка
    for i in range(3):
        try:
            conn = sqlite3.connect(_DB_PATH, timeout=0.5)
            conn.close()
            break
        except:
            time.sleep(0.1)
  
# modules/database.py - добавь в конец файла

def force_release_all_connections():
    """
    Полное принудительное освобождение всех соединений с БД
    Вызывать перед операциями, требующими эксклюзивного доступа
    """
    import gc
    import sqlite3
    
    # 1. Принудительная сборка мусора
    gc.collect()
    gc.collect()  # Двойная сборка для надёжности
    
    # 2. Закрываем все соединения через checkpoint
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=0.5, isolation_level=None)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")  # Временно выключаем WAL
        conn.execute("PRAGMA journal_mode=WAL")      # Включаем обратно
        conn.close()
    except Exception as e:
        logger.debug(f"Checkpoint error: {e}")
    
    # 3. Небольшая пауза для освобождения файловой системы
    time.sleep(0.1)
    
    # 4. Ещё одна сборка мусора
    gc.collect()
    
    logger.info("Все соединения с БД принудительно закрыты")


def is_db_locked():
    """Проверяет, заблокирована ли БД"""
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=0.1)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return False
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return True
        return False
    except:
        return False 
    
# ========== СБРОС БД ==========
def reset_and_recreate_db():
    """Полностью пересоздаёт БД с актуальной структурой"""
    import os
    import sqlite3
    
    db_path = get_db_path()
    
    # Закрываем все соединения
    try:
        conn = sqlite3.connect(db_path, timeout=60.0)
        conn.close()
    except:
        pass
    
    # Удаляем старую БД
    if os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"Старая БД удалена: {db_path}")
    
    # Создаём БД с нуля
    init_local_db()
    
    # Добавляем новые колонки и таблицы
    conn = get_connection()
    cursor = conn.cursor()
    
    # Добавляем domain в licenses
    cursor.execute("PRAGMA table_info(licenses)")
    columns = [c[1] for c in cursor.fetchall()]
    if 'domain' not in columns:
        cursor.execute("ALTER TABLE licenses ADD COLUMN domain TEXT")
        logger.info("Добавлена колонка domain в licenses")
    
    # Добавляем parsed_cache в licenses
    if 'parsed_cache' not in columns:
        cursor.execute("ALTER TABLE licenses ADD COLUMN parsed_cache TEXT")
        logger.info("Добавлена колонка parsed_cache в licenses")
    
    # Создаём dynamic_columns
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
    logger.info("Таблица dynamic_columns создана")
    
    # Создаём dynamic_values
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
    logger.info("Таблица dynamic_values создана")
    
    # Обновляем уникальный индекс
    cursor.execute("DROP INDEX IF EXISTS idx_licenses_unique")
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_unique 
        ON licenses(operator, domain, ne_type, city, site, year, lsn)
    ''')
    logger.info("Уникальный индекс обновлён")
    
    # Добавляем domain в esn_mapping
    cursor.execute("PRAGMA table_info(esn_mapping)")
    columns = [c[1] for c in cursor.fetchall()]
    if 'domain' not in columns:
        cursor.execute("ALTER TABLE esn_mapping ADD COLUMN domain TEXT")
        logger.info("Добавлена колонка domain в esn_mapping")
    
    conn.commit()
    conn.close()
    
    logger.info("БД полностью пересоздана с новой структурой")
    return True

# ========== ТЕСТОВАЯ БД ==========
import tempfile
import shutil

_TEST_DB_PATH = None

def create_test_db():
    """
    Создаёт временную копию БД для тестирования
    Возвращает путь к временной БД
    """
    global _TEST_DB_PATH, _DB_PATH
    
    # Закрываем все соединения с основной БД
    force_release_db()
    
    # Создаём временный файл
    fd, temp_path = tempfile.mkstemp(suffix='.db', prefix='test_licenses_')
    os.close(fd)
    
    # Копируем основную БД (если существует)
    if os.path.exists(_DB_PATH):
        shutil.copy2(_DB_PATH, temp_path)
    else:
        # Если нет - создаём новую
        original_path = _DB_PATH
        _DB_PATH = temp_path
        init_local_db()
        _DB_PATH = original_path
    
    _TEST_DB_PATH = temp_path
    return temp_path


def get_test_connection():
    """
    Получает соединение с тестовой БД
    """
    if _TEST_DB_PATH is None:
        create_test_db()
    
    conn = sqlite3.connect(_TEST_DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def cleanup_test_db():
    """
    Удаляет временную тестовую БД
    """
    global _TEST_DB_PATH
    if _TEST_DB_PATH and os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
            logger.info(f"Тестовая БД удалена: {_TEST_DB_PATH}")
        except Exception as e:
            logger.warning(f"Не удалось удалить тестовую БД: {e}")
        _TEST_DB_PATH = None
        
# Добавь в modules/database.py

def init_test_database():
    """Инициализирует тестовую БД с нуля"""
    global _TEST_DB_PATH, _DB_PATH
    
    if _TEST_DB_PATH and os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)
    
    fd, temp_path = tempfile.mkstemp(suffix='.db', prefix='test_licenses_')
    os.close(fd)
    
    _TEST_DB_PATH = temp_path
    original_path = _DB_PATH
    _DB_PATH = _TEST_DB_PATH
    init_local_db()
    _DB_PATH = original_path
    
    return _TEST_DB_PATH

def refresh_all_targets(operator_name, network_storage_path):
    """Пересчитать цели для всех NE типов оператора"""
    from modules.capacity_mapper import load_targets_from_excel, load_full_capacity_list, compute_license_targets
    import os
    
    targets_file = os.path.join(network_storage_path, 'targets.xlsx')
    if not os.path.exists(targets_file):
        logger.warning(f"Файл целей не найден: {targets_file}")
        return 0
    
    targets = load_targets_from_excel(targets_file, operator_name)
    if not targets:
        logger.warning(f"Нет целей в файле: {targets_file}")
        return 0
    
    # Получаем список уникальных NE типов и доменов
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT l.ne_type, l.domain 
        FROM licenses l 
        WHERE l.operator = ? AND l.ne_type IS NOT NULL AND l.ne_type != ''
    """, (operator_name,))
    ne_types = cursor.fetchall()
    conn.close()
    
    total_results = 0
    
    for ne_type, domain in ne_types:
        logger.info(f"Пересчёт целей для {operator_name}/{ne_type} (domain: {domain})")
        
        capacity_list = load_full_capacity_list(domain, network_storage_path, ne_type, operator_name)
        if not capacity_list:
            logger.warning(f"Нет capacity_list для {ne_type}")
            continue
        
        results = compute_license_targets(targets, capacity_list, operator_name)
        
        if results:
            # Сохраняем в БД
            with get_connection() as conn:
                cursor = conn.cursor()
                # Удаляем старые данные для этого ne_type
                cursor.execute("DELETE FROM license_targets WHERE ne_type = ?", (ne_type,))
                
                # Вставляем новые
                for r in results:
                    cursor.execute("""
                        INSERT INTO license_targets 
                        (operator, target_key, city, ne_type, capacity_key, target_value, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (r['operator'], r['target_key'], r['city'], r['ne_type'], 
                          r['capacity_key'], r['target_value']))
                
                conn.commit()
                total_results += len(results)
                logger.info(f"Сохранено {len(results)} целей для {ne_type}")
    
    return total_results