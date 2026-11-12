# modules/config_store.py
"""
Атомарное чтение/запись секций config.json.
Сохраняет все остальные ключи config.json без изменений.
Содержит:
  - ESN-mapping config (колонки A-G)
  - структуру папок по доменам (folder_structure)
  - шаблон имени лицензии (license_name_template)
  - рендер имени по шаблону (поддержка {create_date}, {create_month_short}, ...)
"""
import json
import os
import tempfile
from datetime import datetime
from modules.logger import get_logger

logger = get_logger(__name__)

CONFIG_PATH = 'config.json'


# ========================================================================
# БАЗОВОЕ ЧТЕНИЕ / ЗАПИСЬ
# ========================================================================

def load_config():
    """Читает config.json целиком. При ошибке — пустой dict."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать {CONFIG_PATH}: {e}")
        return {}


def _atomic_write(config):
    """Атомарная запись через tmp + os.replace."""
    target_dir = os.path.dirname(os.path.abspath(CONFIG_PATH)) or '.'
    fd, tmp_path = tempfile.mkstemp(prefix='.config_', suffix='.json', dir=target_dir)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CONFIG_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def save_config_section(section, data):
    """Сохраняет одну секцию, не трогая остальные ключи."""
    config = load_config()
    config[section] = data
    _atomic_write(config)
    logger.info(f"Секция '{section}' сохранена в {CONFIG_PATH}")


# ========================================================================
# ESN MAPPING CONFIG
# ========================================================================

DEFAULT_ESN_MAPPING_CONFIG = {
    'columns': {
        'esn': 'A',
        'lsn': 'B',
        'operator': 'C',
        'domain': 'D',
        'ne_type': 'E',
        'city': 'F',
        'site': 'G',
    },
    'has_header': True,
}


def get_esn_mapping_config():
    """Возвращает конфиг ESN-маппинга с дефолтами для отсутствующих полей."""
    cfg = load_config().get('esn_mapping_config') or {}
    merged = dict(DEFAULT_ESN_MAPPING_CONFIG)
    merged.update({k: v for k, v in cfg.items() if k != 'columns'})
    merged['columns'] = {
        **DEFAULT_ESN_MAPPING_CONFIG['columns'],
        **(cfg.get('columns') or {}),
    }
    return merged


def set_esn_mapping_config(columns, has_header):
    """Сохраняет конфиг ESN-маппинга."""
    save_config_section('esn_mapping_config', {
        'columns': dict(columns),
        'has_header': bool(has_header),
    })


def col_letter_to_index(letter):
    """A->1, B->2, ..., Z->26, AA->27."""
    if not letter:
        raise ValueError("Пустая буква колонки")
    letter = str(letter).strip().upper()
    idx = 0
    for ch in letter:
        if not ('A' <= ch <= 'Z'):
            raise ValueError(f"Некорректная буква колонки: '{letter}'")
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx


# ========================================================================
# FOLDER STRUCTURE (по доменам)
# ========================================================================

DEFAULT_FOLDER_STRUCTURE = ['operator', 'ne_type', 'city', 'site', 'year']


def get_folder_structure_for_domain(domain):
    """
    Возвращает список уровней для домена.
    Поддерживает две схемы в config.json:
      - list: старый глобальный список → используется для всех доменов
      - dict: {domain: [levels], 'default': [levels]}
    """
    cfg = load_config()
    fs = cfg.get('folder_structure')

    if isinstance(fs, list):
        return fs or DEFAULT_FOLDER_STRUCTURE

    if isinstance(fs, dict):
        if domain and domain in fs and isinstance(fs[domain], list):
            return fs[domain]
        if 'default' in fs and isinstance(fs['default'], list):
            return fs['default']

    return DEFAULT_FOLDER_STRUCTURE


def get_all_folder_structures():
    """
    Возвращает {domain: [levels]} с гарантированным 'default'.
    Старая схема (list) оборачивается в {'default': list}.
    """
    cfg = load_config()
    fs = cfg.get('folder_structure')

    if isinstance(fs, list):
        return {'default': fs or DEFAULT_FOLDER_STRUCTURE}

    if isinstance(fs, dict):
        out = {k: v for k, v in fs.items() if isinstance(v, list) and v}
        out.setdefault('default', DEFAULT_FOLDER_STRUCTURE)
        return out

    return {'default': DEFAULT_FOLDER_STRUCTURE}


# ========================================================================
# LICENSE NAME TEMPLATE
# ========================================================================

DEFAULT_LICENSE_NAME_TEMPLATE = 'LIC{ne_type}_{version}_{city}_{site}_{year}'

MONTH_SHORT_EN = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                  'jul', 'aug', 'sep', 'oct', 'nov', 'dec']


def get_license_name_template():
    """Возвращает шаблон имени лицензии (без расширения)."""
    cfg = load_config()
    return (cfg.get('license_name_template') or DEFAULT_LICENSE_NAME_TEMPLATE).strip()


# ========================================================================
# DATE PARSING (create_time)
# ========================================================================

def _parse_create_date(raw):
    """
    Разбирает строку даты создания и возвращает dict:
      {'year': 'YYYY', 'month': 'MM', 'day': 'DD',
       'month_short': 'jan'..'dec', 'date': 'YYYY-MM-DD'}
    Если распарсить не удалось — все значения пустые строки.

    Поддерживаемые форматы:
      'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DDTHH:MM:SS',
      'YYYY-MM-DD', 'YYYY/MM/DD', 'DD.MM.YYYY'
    """
    empty = {'year': '', 'month': '', 'day': '', 'month_short': '', 'date': ''}
    if not raw:
        return empty

    s = str(raw).strip()

    # Порядок — от самого длинного к короткому
    formats = (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d.%m.%Y',
    )

    for fmt in formats:
        try:
            # strptime ожидает ровно столько символов, сколько в формате.
            # Для короткого формата берём короткий срез, для длинного — длинный.
            expected_len = len(datetime.now().strftime(fmt))
            candidate = s[:expected_len]
            dt = datetime.strptime(candidate, fmt)
            return {
                'year': f'{dt.year:04d}',
                'month': f'{dt.month:02d}',
                'day': f'{dt.day:02d}',
                'month_short': MONTH_SHORT_EN[dt.month - 1],
                'date': f'{dt.year:04d}-{dt.month:02d}-{dt.day:02d}',
            }
        except ValueError:
            continue

    return empty


# ========================================================================
# RENDER LICENSE BASENAME (единственная функция, без дубликатов)
# ========================================================================

def render_license_basename(template, values):
    """
    Подставляет {placeholder} в шаблоне значениями из values.
    Дополнительно (независимо от values) поддерживает:
      {create_date}        → YYYY-MM-DD
      {create_year}        → YYYY
      {create_month}       → MM
      {create_month_short} → jan..dec
      {create_day}         → DD
    Основа — values.get('create_time').
    Возвращает строку без расширения (расширение добавляет вызывающий код).
    """
    d = _parse_create_date(values.get('create_time'))

    merged = {
        **values,
        'create_date': d['date'],
        'create_year': d['year'],
        'create_month': d['month'],
        'create_month_short': d['month_short'],
        'create_day': d['day'],
    }

    out = str(template or '')
    for k, v in merged.items():
        out = out.replace('{' + k + '}', '' if v is None else str(v))
    return out