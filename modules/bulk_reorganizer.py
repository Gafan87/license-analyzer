# modules/bulk_reorganizer.py
"""
Массовое переименование и/или раскладка лицензий по правилам из config.json.

operation:
  'rename' — только переименовать (файл остаётся в своей папке)
  'move'   — только разложить по структуре (имя файла не меняется)
  'both'   — и переименовать, и разложить

copy_mode=True — копирование вместо перемещения (безопасно).
"""
import os
import re
import shutil
from modules.database import get_connection
from modules.logger import get_logger
from modules.config_store import (
    get_folder_structure_for_domain,
    get_license_name_template,
    render_license_basename,
)

logger = get_logger(__name__)

VALID_OPERATIONS = ('rename', 'move', 'both')


def _row_to_dict(row, columns):
    return dict(zip(columns, row))


def _calc_year_folder(valid_date, fallback_year):
    if valid_date and valid_date not in ('PERMANENT', 'UNKNOWN'):
        m = re.match(r'(\d{4})-(\d{2})', valid_date)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            return str(year - 1) if month <= 3 else str(year)
    return fallback_year or 'permanent'


def _build_filename(lic):
    """Возвращает новое имя файла (с расширением) по шаблону."""
    domain = lic.get('domain') or 'Unknown'
    year_folder = _calc_year_folder(lic.get('valid_date'), lic.get('year'))

    path_values = {
        'operator': lic.get('operator') or 'Unknown',
        'domain': domain,
        'ne_type': lic.get('ne_type') or 'Unknown',
        'city': lic.get('city') or 'Unknown',
        'site': lic.get('site') or 'Unknown',
        'year': year_folder,
        'version': lic.get('version') or 'unknown',
        'lsn': lic.get('lsn') or '',
        'esn': lic.get('esn') or '',
    }

    template = get_license_name_template()
    base = render_license_basename(template, {
        **path_values,
        'create_time': lic.get('create_time') or '',
    })
    base = re.sub(r'[^\w\-.]', '_', base)

    ext = os.path.splitext(lic.get('filename') or '')[1] or '.dat'
    return base + ext


def _build_target_dir(remote_base, lic):
    """Возвращает директорию на шаре по folder_structure[domain]."""
    domain = lic.get('domain') or 'Unknown'
    year_folder = _calc_year_folder(lic.get('valid_date'), lic.get('year'))

    path_values = {
        'operator': lic.get('operator') or 'Unknown',
        'domain': domain,
        'ne_type': lic.get('ne_type') or 'Unknown',
        'city': lic.get('city') or 'Unknown',
        'site': lic.get('site') or 'Unknown',
        'year': year_folder,
        'version': lic.get('version') or 'unknown',
        'lsn': lic.get('lsn') or '',
        'esn': lic.get('esn') or '',
    }

    levels = get_folder_structure_for_domain(domain)
    parts = [
        re.sub(r'[^\w\-.]', '_', str(path_values.get(lvl, 'Unknown')) or 'Unknown')
        for lvl in levels
    ]
    return os.path.join(remote_base, *parts)


def _target_path(remote_base, lic, operation):
    """Возвращает новый полный путь файла для заданной операции."""
    old_path = lic.get('local_path') or ''
    old_filename = lic.get('filename') or (os.path.basename(old_path) if old_path else '')

    if operation == 'rename':
        # Остаётся в своей папке, меняется только имя
        target_dir = os.path.dirname(old_path) if old_path else ''
        new_filename = _build_filename(lic)
        return os.path.join(target_dir, new_filename) if target_dir else new_filename

    if operation == 'move':
        # Едет в новую папку, имя не меняется
        target_dir = _build_target_dir(remote_base, lic)
        return os.path.join(target_dir, old_filename) if old_filename else target_dir

    # both
    target_dir = _build_target_dir(remote_base, lic)
    new_filename = _build_filename(lic)
    return os.path.join(target_dir, new_filename)


def preview(operator, remote_base, operation='both'):
    """
    Возвращает список {id, lsn, old_path, new_path, status, reason}.
    Файлы НЕ двигаются. Только чтение БД и расчёт.
    """
    if operation not in VALID_OPERATIONS:
        raise ValueError(f"operation должен быть один из {VALID_OPERATIONS}")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, operator, domain, ne_type, city, site, year, version,
               lsn, esn, valid_date, filename, local_path, create_time
        FROM licenses WHERE operator = ?
    ''', (operator,))
    cols = [d[0] for d in cursor.description]
    rows = [_row_to_dict(r, cols) for r in cursor.fetchall()]
    conn.close()

    out = []
    for lic in rows:
        old_path = lic.get('local_path') or ''
        try:
            new_path = _target_path(remote_base, lic, operation)
        except Exception as e:
            out.append({
                'id': lic['id'], 'lsn': lic.get('lsn') or '',
                'old_path': old_path, 'new_path': '',
                'status': 'error', 'reason': f'ошибка расчёта: {e}',
            })
            continue

        if not old_path:
            status, reason = 'skip', 'нет local_path'
        elif not os.path.exists(old_path):
            status, reason = 'skip', 'файл не найден по local_path'
        elif os.path.normpath(old_path) == os.path.normpath(new_path):
            status, reason = 'skip', 'уже на месте'
        elif os.path.exists(new_path):
            status, reason = 'conflict', 'целевой файл уже существует'
        else:
            status, reason = 'ok', ''

        out.append({
            'id': lic['id'], 'lsn': lic.get('lsn') or '',
            'old_path': old_path, 'new_path': new_path,
            'status': status, 'reason': reason,
        })
    return out


def apply(operator, remote_base, operation='both', copy_mode=False):
    """
    Применяет операцию. copy_mode=True — копирование вместо перемещения.
    Возвращает {moved, skipped, conflicts, errors, copy_mode, operation, details}.
    """
    if operation not in VALID_OPERATIONS:
        raise ValueError(f"operation должен быть один из {VALID_OPERATIONS}")

    items = preview(operator, remote_base, operation)
    moved = skipped = conflicts = errors = 0
    details = []

    conn = get_connection()
    cursor = conn.cursor()

    for it in items:
        if it['status'] == 'skip':
            skipped += 1
            details.append({**it, 'result': 'skipped'})
            continue
        if it['status'] == 'conflict':
            conflicts += 1
            details.append({**it, 'result': 'conflict'})
            continue
        if it['status'] == 'error':
            errors += 1
            details.append({**it, 'result': 'error'})
            continue

        try:
            os.makedirs(os.path.dirname(it['new_path']), exist_ok=True)
            if copy_mode:
                shutil.copy2(it['old_path'], it['new_path'])
            else:
                shutil.move(it['old_path'], it['new_path'])

            new_filename = os.path.basename(it['new_path'])
            cursor.execute(
                'UPDATE licenses SET local_path = ?, filename = ? WHERE id = ?',
                (it['new_path'], new_filename, it['id']),
            )
            moved += 1
            details.append({**it, 'result': 'copied' if copy_mode else 'moved'})
        except Exception as e:
            verb = 'копирования' if copy_mode else 'перемещения'
            logger.error(f"Ошибка {verb} id={it['id']}: {e}")
            errors += 1
            details.append({**it, 'result': 'error', 'reason': str(e)})

    conn.commit()
    conn.close()

    return {
        'success': True,
        'operation': operation,
        'copy_mode': copy_mode,
        'moved': moved,
        'skipped': skipped,
        'conflicts': conflicts,
        'errors': errors,
        'details': details,
    }