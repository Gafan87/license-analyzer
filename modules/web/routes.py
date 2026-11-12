# modules/web/routes.py
"""Web routes for License Analyzer"""
import os
import re
import json
import shutil
import logging
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session, current_app, abort

from modules.database import (
    get_connection, get_licenses, get_license_by_id, get_resources,
    get_all_tags, get_license_tags, add_tag_to_license, remove_tag_from_license,
    get_comments, add_comment, delete_comment, create_tag,
    get_dynamic_values_for_license, update_parsed_cache, get_parsed_cache,
    get_all_licenses_with_aggregated,
    get_unique_esn_licenses, get_all_licenses_for_esn, save_license,
    get_extraction_rules, save_extraction_rules,
    backup_db, get_expiring_licenses, get_operator_statistics,
    get_history_records, delete_history_record, get_rename_history,
    get_db_stats
)
from modules.config_store import get_esn_mapping_config
from modules.excel_importer import import_excel, preview_excel
from modules.export_manager import export_licenses

logger = logging.getLogger(__name__)
web_bp = Blueprint('web', __name__)


def get_operator_config(operator):
    """Получить конфигурацию оператора"""
    operators = current_app.config.get('OPERATORS', [])
    return next((op for op in operators if op['name'] == operator), None)


@web_bp.route('/')
def root():
    """Редирект на главную первого оператора"""
    operators = current_app.config.get('OPERATORS', [])
    if operators:
        return redirect(url_for('web.index', operator=operators[0]['name']))
    return render_template('index.html', licenses=[], operators=[])


@web_bp.route('/help')
def help_page():
    """Справка по рабочему процессу и основным модулям программы."""
    operators = current_app.config.get('OPERATORS', [])
    current_operator = session.get('current_operator', operators[0]['name'] if operators else '')
    current_operator_title = next(
        (op.get('title', op['name']) for op in operators if op['name'] == current_operator),
        current_operator
    )
    return render_template('help.html',
                          operators=operators,
                          current_operator=current_operator,
                          current_operator_title=current_operator_title)


@web_bp.route('/dashboard')
def dashboard():
    """Дашборд со статистикой"""
    operators = current_app.config.get('OPERATORS', [])
    
    stats = {}
    total_licenses = 0
    total_expiring = 0
    
    for op in operators:
        op_stats = get_operator_statistics(op['name'])
        stats[op['name']] = op_stats
        total_licenses += op_stats.get('total', 0)
        total_expiring += op_stats.get('expiring_30', 0)
    current_operator = session.get('current_operator', operators[0]['name'] if operators else '')
    current_operator_title = next(
        (op.get('title', op['name']) for op in operators if op['name'] == current_operator),
        current_operator
    )
    
    return render_template('dashboard.html',
                          operators=operators,
                          stats=stats,
                          total_licenses=total_licenses,
                          total_expiring=total_expiring,
                          current_operator=current_operator,
                          current_operator_title=current_operator_title)


@web_bp.route('/<operator>/')
def index(operator):
    """Главная страница оператора с таблицей лицензий"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    session['current_operator'] = operator
    
    # Параметры фильтрации
    filters = {
        'esn': request.args.get('esn', '').strip(),
        'ne_type': request.args.get('ne_type', '').strip(),
        'city': request.args.get('city', '').strip(),
        'site': request.args.get('site', '').strip(),
        'year': request.args.get('year', '').strip(),
        'domain': request.args.get('domain', '').strip(),
        'tag': request.args.get('tag', '').strip(),
        'expiring': request.args.get('expiring', type=int),
        'search': request.args.get('search', '').strip(),
    }
    # Убираем пустые фильтры
    filters = {k: v for k, v in filters.items() if v}
    
    # Пагинация
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 500)  # Максимум 500
    
    # Получаем лицензии
    result = get_licenses(operator, filters=filters, page=page, per_page=per_page)
    
    # Получаем теги для фильтра
    tags = get_all_tags()
    
    # Статистика
    stats = get_operator_statistics(operator)
    
    # Динамические колонки
    from modules.database import get_dynamic_columns
    dynamic_columns = get_dynamic_columns()
    
    return render_template('index.html',
                          licenses=result['licenses'],
                          pagination=result['pagination'],
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator),
                          filters=filters,
                          tags=tags,
                          stats=stats,
                          dynamic_columns=dynamic_columns)


@web_bp.route('/<operator>/license/<int:license_id>')
def license_detail(operator, license_id):
    """Детальная страница лицензии"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    lic = get_license_by_id(license_id)
    if not lic:
        abort(404)
    
    # Добавляем связанные данные
    lic['tags'] = get_license_tags(license_id)
    lic['comments'] = get_comments(license_id)
    lic['dynamic_values'] = get_dynamic_values_for_license(license_id)
    
    return render_template('license_detail.html',
                          license=lic,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/reports')
def reports(operator):
    """Страница отчётов"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    return render_template('reports.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/history')
def history(operator):
    """История операций"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    records = get_history_records(operator)
    
    return render_template('history.html',
                          records=records,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/expiring')
def expiring(operator):
    """Истекающие лицензии"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    days = request.args.get('days', 30, type=int)
    licenses = get_expiring_licenses(operator, days)
    
    return render_template('expiring.html',
                          licenses=licenses,
                          days=days,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/rename_files')
def rename_files(operator):
    """Переименование файлов"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    history_records = get_rename_history(operator)
    
    return render_template('rename_files.html',
                          history=history_records,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/report_templates')
def report_templates(operator):
    """Шаблоны отчётов"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    from modules.report_templates import get_all_templates
    templates = get_all_templates(operator)
    
    return render_template('report_templates.html',
                          templates=templates,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/settings')
def settings():
    """Страница настроек"""
    from modules.config_store import load_config
    config = load_config()
    operators = current_app.config.get('OPERATORS', [])
    current_operator = session.get('current_operator', operators[0]['name'] if operators else '')
    current_operator_title = next(
        (op.get('title', op['name']) for op in operators if op['name'] == current_operator),
        current_operator
    )
    
    return render_template('settings.html',
                          config=config,
                          operators=operators,
                          current_operator=current_operator,
                          current_operator_title=current_operator_title,
                          debug_settings=config.get('debug_settings', {}),
                          backups=get_backup_list())


@web_bp.route('/settings/debug', methods=['POST'])
def update_debug_settings():
    """Сохраняет только режимы интерфейса, не изменяя остальные секции config.json."""
    from modules.config_store import load_config, save_config_section

    debug_settings = load_config().get('debug_settings') or {}
    debug_settings['show_tooltips'] = request.form.get('show_tooltips') == '1'
    save_config_section('debug_settings', debug_settings)
    current_app.config['debug_settings'] = debug_settings

    flash('Настройки подсказок сохранены', 'success')
    return redirect(url_for('web.settings') + '#testing')


def get_backup_list():
    """Получить список бэкапов БД"""
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    if not os.path.exists(backup_dir):
        return []
    
    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith('.db'):
            path = os.path.join(backup_dir, f)
            stat = os.stat(path)
            backups.append({
                'name': f,
                'size': stat.st_size,
                'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return sorted(backups, key=lambda x: x['date'], reverse=True)


@web_bp.route('/style_guide')
def style_guide():
    """Руководство по стилю"""
    return render_template('style_guide.html')


# ========== API ROUTES ==========

@web_bp.route('/<operator>/scan', methods=['POST'])
def scan_licenses(operator):
    """Запустить сканирование лицензий"""
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'success': False, 'message': 'Оператор не найден'}), 404
    
    try:
        from modules.scanner import scan_operator_licenses
        result = scan_operator_licenses(operator)
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error(f"Ошибка сканирования: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/<operator>/sync', methods=['POST'])
def sync_licenses(operator):
    """Синхронизация с сетевым хранилищем"""
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'success': False, 'message': 'Оператор не найден'}), 404
    
    try:
        from modules.sync_manager import sync_operator
        network_storage_path = current_app.config.get('network_storage_path', '')
        result = sync_operator(operator, network_storage_path)
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error(f"Ошибка синхронизации: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/<operator>/scan_status')
def scan_status(operator):
    """Статус сканирования"""
    # TODO: Реализовать отслеживание прогресса
    return jsonify({'status': 'idle', 'progress': 0})


@web_bp.route('/download_db')
def download_db():
    """Скачать БД"""
    from flask import send_file
    db_path = current_app.config.get('DB_PATH', 'local_licenses.db')
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True, download_name='local_licenses.db')
    return jsonify({'error': 'БД не найдена'}), 404


@web_bp.route('/import_excel', methods=['POST'])
def import_excel_route():
    """Импорт из Excel"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    try:
        # Сохраняем временно
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file.save(tmp.name)
            result = import_excel(tmp.name)
            os.unlink(tmp.name)
        
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error(f"Ошибка импорта: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/tags', methods=['POST'])
def api_create_tag():
    """Создать тег"""
    data = request.get_json()
    name = data.get('name', '').strip()
    color = data.get('color', '#6c757d')
    
    if not name:
        return jsonify({'success': False, 'message': 'Название обязательно'}), 400
    
    tag_id = create_tag(name, color)
    return jsonify({'success': True, 'id': tag_id})


@web_bp.route('/api/license/<int:license_id>/tags', methods=['POST'])
def api_add_tag(license_id):
    """Добавить тег к лицензии"""
    data = request.get_json()
    tag_id = data.get('tag_id')
    
    add_tag_to_license(license_id, tag_id)
    return jsonify({'success': True})


@web_bp.route('/api/license/<int:license_id>/tags/<int:tag_id>', methods=['DELETE'])
def api_remove_tag(license_id, tag_id):
    """Удалить тег с лицензии"""
    remove_tag_from_license(license_id, tag_id)
    return jsonify({'success': True})


@web_bp.route('/api/license/<int:license_id>/comments', methods=['POST'])
def api_add_comment(license_id):
    """Добавить комментарий"""
    data = request.get_json()
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({'success': False, 'message': 'Текст обязателен'}), 400
    
    comment_id = add_comment(license_id, text)
    return jsonify({'success': True, 'id': comment_id})


@web_bp.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def api_delete_comment(comment_id):
    """Удалить комментарий"""
    delete_comment(comment_id)
    return jsonify({'success': True})


@web_bp.route('/api/export', methods=['POST'])
def api_export():
    """Экспорт лицензий"""
    data = request.get_json()
    operator = data.get('operator')
    license_ids = data.get('license_ids', [])
    columns = data.get('columns', [])
    
    try:
        output = export_licenses(operator, license_ids, columns)
        return jsonify({'success': True, 'data': output})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/settings/paths', methods=['POST'])
def api_save_paths():
    """Сохранить пути"""
    from modules.config_store import load_config, save_config
    
    data = request.get_json()
    config = load_config()
    
    if 'network_storage_path' in data:
        config['network_storage_path'] = data['network_storage_path']
    if 'targets_file' in data:
        config['targets_file'] = data['targets_file']
    
    save_config(config)
    return jsonify({'success': True})


@web_bp.route('/api/settings/storage', methods=['POST'])
def api_save_storage():
    """Сохранить настройки хранения"""
    from modules.config_store import save_config_section
    
    data = request.get_json()
    save_config_section('storage_settings', data)
    return jsonify({'success': True})


@web_bp.route('/api/backup', methods=['POST'])
def api_backup():
    """Создать бэкап БД"""
    path = backup_db()
    return jsonify({'success': True, 'path': path})


@web_bp.route('/api/restore', methods=['POST'])
def api_restore():
    """Восстановить из бэкапа"""
    data = request.get_json()
    backup_path = data.get('path')
    
    if not backup_path or not os.path.exists(backup_path):
        return jsonify({'success': False, 'message': 'Бэкап не найден'}), 404
    
    try:
        db_path = current_app.config.get('DB_PATH', 'local_licenses.db')
        shutil.copy2(backup_path, db_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    """Очистить логи"""
    try:
        log_dir = current_app.config.get('LOG_DIR', 'logs')
        for f in os.listdir(log_dir):
            if f.endswith('.log'):
                os.remove(os.path.join(log_dir, f))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/reset_db', methods=['POST'])
def api_reset_db():
    """Сбросить БД"""
    try:
        db_path = current_app.config.get('DB_PATH', 'local_licenses.db')
        if os.path.exists(db_path):
            os.remove(db_path)
        
        from modules.database import init_db
        init_db()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/tests/run', methods=['POST'])
def api_run_tests():
    """Запустить тесты"""
    import subprocess
    
    data = request.get_json() or {}
    category = data.get('category', 'all')
    test_name = data.get('test')
    
    cmd = ['python', '-m', 'pytest', 'tests/', '-v']
    if category != 'all':
        cmd = ['python', '-m', 'pytest', f'tests/test_{category}.py', '-v']
    if test_name:
        cmd.append(f'-k {test_name}')
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ========== НОВЫЕ МАРШРУТЫ ДЛЯ ПОЛНОЦЕННОГО ИНТЕРФЕЙСА ==========

@web_bp.route('/<operator>/report/<int:report_id>')
def view_report(operator, report_id):
    """Просмотр сохранённого отчёта"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    from modules.report_templates import get_template_by_id
    report = get_template_by_id(report_id)
    if not report:
        abort(404)
    
    return render_template('view_report.html',
                          report=report,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/compare')
def compare_licenses(operator):
    """Сравнение лицензий"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    ids = request.args.get('ids', '')
    license_ids = [int(x) for x in ids.split(',') if x.strip().isdigit()]
    
    licenses = []
    for lid in license_ids[:10]:  # Максимум 10
        lic = get_license_by_id(lid)
        if lic:
            licenses.append(lic)
    
    return render_template('compare.html',
                          licenses=licenses,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/esn_mapping')
def esn_mapping(operator):
    """ESN маппинг"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    return render_template('esn_mapping.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator),
                          esn_config=get_esn_mapping_config())


# ========== API ДЛЯ ДИНАМИЧЕСКИХ ПОЛЕЙ ==========

@web_bp.route('/api/dynamic_fields', methods=['GET'])
def api_get_dynamic_fields():
    """Получить динамические поля"""
    from modules.database import get_dynamic_columns
    return jsonify(get_dynamic_columns())


@web_bp.route('/api/dynamic_fields', methods=['POST'])
def api_create_dynamic_field():
    """Создать динамическое поле"""
    from modules.database import add_dynamic_column
    
    data = request.get_json()
    column_id = add_dynamic_column(
        data['column_name'],
        data['display_name'],
        data.get('rule_id'),
        data.get('capacity_key'),
        data.get('aggregation_strategy', 'sum'),
        data.get('join_separator', ', ')
    )
    return jsonify({'success': True, 'id': column_id})


@web_bp.route('/api/dynamic_fields/<int:field_id>', methods=['DELETE'])
def api_delete_dynamic_field(field_id):
    """Удалить динамическое поле"""
    from modules.database import delete_dynamic_column
    delete_dynamic_column(field_id)
    return jsonify({'success': True})


@web_bp.route('/api/dynamic_fields/<int:field_id>', methods=['PUT'])
def api_update_dynamic_field(field_id):
    """Обновить динамическое поле"""
    from modules.database import update_dynamic_column
    
    data = request.get_json()
    update_dynamic_column(field_id, **data)
    return jsonify({'success': True})


# ========== API ДЛЯ ПРАВИЛ ИЗВЛЕЧЕНИЯ ==========

@web_bp.route('/api/extraction_rules', methods=['GET'])
def api_get_rules():
    """Получить правила извлечения"""
    return jsonify(get_extraction_rules())


@web_bp.route('/api/extraction_rules', methods=['POST'])
def api_save_rules():
    """Сохранить правила извлечения"""
    data = request.get_json()
    save_extraction_rules(data)
    return jsonify({'success': True})


# ========== API ДЛЯ МАССОВЫХ ОПЕРАЦИЙ ==========

@web_bp.route('/api/bulk/tags', methods=['POST'])
def api_bulk_tags():
    """Массовое добавление/удаление тегов"""
    data = request.get_json()
    license_ids = data.get('license_ids', [])
    tag_id = data.get('tag_id')
    action = data.get('action', 'add')
    
    for lid in license_ids:
        if action == 'add':
            add_tag_to_license(lid, tag_id)
        else:
            remove_tag_from_license(lid, tag_id)
    
    return jsonify({'success': True, 'count': len(license_ids)})


@web_bp.route('/api/bulk/delete', methods=['POST'])
def api_bulk_delete():
    """Массовое удаление лицензий"""
    from modules.database import delete_license
    
    data = request.get_json()
    license_ids = data.get('license_ids', [])
    
    for lid in license_ids:
        delete_license(lid)
    
    return jsonify({'success': True, 'count': len(license_ids)})


# ========== СТАТИСТИКА И МОНИТОРИНГ ==========

@web_bp.route('/api/stats/<operator>')
def api_operator_stats(operator):
    """Статистика оператора"""
    stats = get_operator_statistics(operator)
    return jsonify(stats)


@web_bp.route('/api/stats')
def api_global_stats():
    """Общая статистика"""
    stats = get_db_stats()
    return jsonify(stats)


@web_bp.route('/api/health')
def api_health():
    """Проверка здоровья системы"""
    try:
        conn = get_connection()
        conn.execute('SELECT 1')
        conn.close()
        db_ok = True
    except:
        db_ok = False
    
    return jsonify({
        'status': 'ok' if db_ok else 'error',
        'database': db_ok,
        'timestamp': datetime.now().isoformat()
    })


# ========== ОБРАБОТКА ОШИБОК ==========

@web_bp.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@web_bp.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return render_template('500.html'), 500





# ========== ДОБАВЛЕННЫЕ МАРШРУТЫ ==========

@web_bp.route('/api/capacity_mapping', methods=['GET'])
def api_get_capacity_mapping():
    """Получить все соответствия CapacityKey"""
    from modules.capacity_mapper import get_mapping
    mapping = get_mapping()
    return jsonify(mapping)


@web_bp.route('/api/capacity_mapping', methods=['POST'])
def api_save_capacity_mapping():
    """Сохранить соответствие CapacityKey"""
    from modules.capacity_mapper import add_mapping
    
    data = request.get_json()
    capacity_key = data.get('capacity_key', '').strip()
    spart = data.get('spart', '').strip()
    bpart = data.get('bpart', '').strip()
    operator = data.get('operator', '').strip() or None
    
    if not capacity_key or not spart or not bpart:
        return jsonify({'success': False, 'message': 'Все поля обязательны'}), 400
    
    add_mapping(capacity_key, spart, bpart, operator)
    return jsonify({'success': True})


@web_bp.route('/api/capacity_mapping/<int:mapping_id>', methods=['DELETE'])
def api_delete_capacity_mapping(mapping_id):
    """Удалить соответствие"""
    from modules.capacity_mapper import delete_mapping
    delete_mapping(mapping_id)
    return jsonify({'success': True})


@web_bp.route('/<operator>/resources/<int:license_id>')
def api_get_license_resources(operator, license_id):
    """Получить ресурсы лицензии с группировкой SPart/BPart"""
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'success': False, 'message': 'Оператор не найден'}), 404
    
    from modules.capacity_mapper import get_grouped_resources
    
    # Параметры
    filter_empty = request.args.get('filter_empty', 'true').lower() == 'true'
    capacity_keys = request.args.getlist('capacity_keys')
    only_with_spart = request.args.get('only_with_spart', 'false').lower() == 'true'
    
    resources = get_grouped_resources(
        license_id=license_id,
        operator=operator,
        filter_empty=filter_empty,
        capacity_keys=capacity_keys if capacity_keys else None,
        only_with_spart=only_with_spart
    )
    
    return jsonify(resources)


@web_bp.route('/<operator>/available_keys')
def api_available_keys(operator):
    """Получить доступные CapacityKey для оператора"""
    from modules.capacity_mapper import get_available_keys
    keys = get_available_keys(operator)
    return jsonify(keys)


@web_bp.route('/api/settings/levels', methods=['POST'])
def api_save_levels():
    """Сохранить настройки уровней структуры папок"""
    from modules.config_store import load_config, save_config
    
    data = request.get_json()
    config = load_config()
    config['folder_levels'] = data.get('levels', [])
    save_config(config)
    
    return jsonify({'success': True})


@web_bp.route('/api/rename/preview', methods=['POST'])
def api_rename_preview():
    """Предпросмотр переименования"""
    from modules.renamer import preview_rename
    
    data = request.get_json()
    operator = data.get('operator')
    
    result = preview_rename(operator)
    return jsonify(result)


@web_bp.route('/api/rename/apply', methods=['POST'])
def api_rename_apply():
    """Применить переименование"""
    from modules.renamer import apply_rename
    
    data = request.get_json()
    operator = data.get('operator')
    items = data.get('items', [])
    
    result = apply_rename(operator, items)
    return jsonify(result)


@web_bp.route('/api/report_templates', methods=['POST'])
def api_save_report_template():
    """Сохранить шаблон отчёта"""
    from modules.report_templates import save_template
    
    data = request.get_json()
    template_id = save_template(data)
    return jsonify({'success': True, 'id': template_id})


@web_bp.route('/api/report_templates/<int:template_id>', methods=['DELETE'])
def api_delete_report_template(template_id):
    """Удалить шаблон отчёта"""
    from modules.report_templates import delete_template
    delete_template(template_id)
    return jsonify({'success': True})


@web_bp.route('/api/report_templates/<int:template_id>/apply', methods=['POST'])
def api_apply_report_template(template_id):
    """Применить шаблон отчёта"""
    from modules.report_templates import get_template_by_id
    
    template = get_template_by_id(template_id)
    if not template:
        return jsonify({'success': False, 'message': 'Шаблон не найден'}), 404
    
    return jsonify({'success': True, 'config': template.get('config', {})})


# ========== ДОПОЛНИТЕЛЬНЫЕ API ДЛЯ ПОЛНОЙ ФУНКЦИОНАЛЬНОСТИ ==========

@web_bp.route('/api/license/<int:license_id>/history')
def api_license_history(license_id):
    """История изменений лицензии"""
    from modules.database import get_license_history
    history = get_license_history(license_id)
    return jsonify(history)


@web_bp.route('/api/license/<int:license_id>/related')
def api_related_licenses(license_id):
    """Связанные лицензии (тот же ESN)"""
    lic = get_license_by_id(license_id)
    if not lic:
        return jsonify([])
    
    related = get_all_licenses_for_esn(lic['operator'], lic['esn'])
    return jsonify(related)


@web_bp.route('/api/search/suggestions')
def api_search_suggestions():
    """Подсказки для поиска"""
    query = request.args.get('q', '').strip()
    operator = request.args.get('operator', '')
    
    if not query or len(query) < 2:
        return jsonify([])
    
    suggestions = []
    conn = get_connection()
    cursor = conn.cursor()
    
    # ESN
    cursor.execute('SELECT DISTINCT esn FROM licenses WHERE esn LIKE ? LIMIT 5', (f'%{query}%',))
    for row in cursor.fetchall():
        suggestions.append({'type': 'esn', 'value': row[0]})
    
    # City
    cursor.execute('SELECT DISTINCT city FROM licenses WHERE city LIKE ? LIMIT 5', (f'%{query}%',))
    for row in cursor.fetchall():
        suggestions.append({'type': 'city', 'value': row[0]})
    
    # Site
    cursor.execute('SELECT DISTINCT site FROM licenses WHERE site LIKE ? LIMIT 5', (f'%{query}%',))
    for row in cursor.fetchall():
        suggestions.append({'type': 'site', 'value': row[0]})
    
    conn.close()
    return jsonify(suggestions)


@web_bp.route('/api/export/excel', methods=['POST'])
def api_export_excel():
    """Экспорт в Excel файл"""
    from flask import send_file
    import tempfile
    from modules.export_manager import export_to_excel_file
    
    data = request.get_json()
    operator = data.get('operator')
    license_ids = data.get('license_ids', [])
    columns = data.get('columns', [])
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            export_to_excel_file(operator, license_ids, columns, tmp.name)
            return send_file(tmp.name, as_attachment=True, 
                           download_name=f'licenses_{operator}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/import/preview', methods=['POST'])
def api_import_preview():
    """Предпросмотр импорта Excel"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file.save(tmp.name)
            result = preview_excel(tmp.name)
            os.unlink(tmp.name)
        
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/notifications')
def api_notifications():
    """Получить уведомления"""
    notifications = []
    
    # Истекающие лицензии
    for op in current_app.config.get('OPERATORS', []):
        expiring = get_expiring_licenses(op['name'], 7)
        if expiring:
            notifications.append({
                'type': 'warning',
                'title': f"{op['title']}: истекают лицензии",
                'message': f"{len(expiring)} лицензий истекают в течение 7 дней",
                'link': url_for('web.expiring', operator=op['name'], days=7)
            })
    
    return jsonify(notifications)


@web_bp.route('/api/backup/list')
def api_backup_list():
    """Список бэкапов"""
    return jsonify(get_backup_list())


@web_bp.route('/api/backup/create', methods=['POST'])
def api_backup_create():
    """Создать бэкап с описанием"""
    data = request.get_json() or {}
    description = data.get('description', '')
    
    path = backup_db(description)
    return jsonify({'success': True, 'path': path})


@web_bp.route('/api/system/info')
def api_system_info():
    """Информация о системе"""
    import sys
    
    stats = get_db_stats()
    
    return jsonify({
        'python_version': sys.version,
        'database': stats,
        'operators': len(current_app.config.get('OPERATORS', [])),
        'debug': current_app.debug
    })



# ========== ДОБАВЛЕННЫЕ МАРШРУТЫ ДЛЯ ШАБЛОНОВ ==========

@web_bp.route('/api/report_templates', methods=['GET'])
def api_get_report_templates():
    """Получить все шаблоны отчётов"""
    operator = request.args.get('operator')
    from modules.report_templates import get_all_templates
    templates = get_all_templates(operator)
    return jsonify(templates)


@web_bp.route('/api/rename/history')
def api_rename_history():
    """История переименований"""
    operator = request.args.get('operator')
    history = get_rename_history(operator)
    return jsonify(history)


@web_bp.route('/api/license/<int:license_id>/resources')
def api_license_resources(license_id):
    """Получить ресурсы лицензии"""
    resources = get_resources(license_id)
    return jsonify(resources)


@web_bp.route('/api/license/<int:license_id>/parse', methods=['POST'])
def api_parse_license(license_id):
    """Перепарсить лицензию"""
    lic = get_license_by_id(license_id)
    if not lic:
        return jsonify({'success': False, 'message': 'Лицензия не найдена'}), 404
    
    try:
        from modules.parsers import parse_license_file
        result = parse_license_file(lic['local_path'])
        
        # Обновляем кэш
        update_parsed_cache(license_id, result)
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/capacity_mapping/import', methods=['POST'])
def api_import_capacity_mapping():
    """Импорт соответствий из Excel"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    
    try:
        from modules.capacity_mapper import import_mapping_from_excel
        import tempfile
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file.save(tmp.name)
            result = import_mapping_from_excel(tmp.name)
            os.unlink(tmp.name)
        
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/capacity_mapping/export')
def api_export_capacity_mapping():
    """Экспорт соответствий в Excel"""
    from flask import send_file
    from modules.capacity_mapper import export_mapping_to_excel
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        export_mapping_to_excel(tmp.name)
        return send_file(tmp.name, as_attachment=True, download_name='capacity_mapping.xlsx')


@web_bp.route('/<operator>/resources')
def operator_resources(operator):
    """Страница ресурсов оператора"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    from modules.capacity_mapper import get_available_keys
    keys = get_available_keys(operator)
    
    return render_template('resources.html',
                          capacity_keys=keys,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/api/settings/export')
def api_export_settings():
    """Экспорт настроек"""
    from modules.config_store import load_config
    config = load_config()
    return jsonify(config)


@web_bp.route('/api/settings/import', methods=['POST'])
def api_import_settings():
    """Импорт настроек"""
    from modules.config_store import save_config
    
    data = request.get_json()
    save_config(data)
    return jsonify({'success': True})


@web_bp.route('/api/db/optimize', methods=['POST'])
def api_optimize_db():
    """Оптимизация БД"""
    try:
        conn = get_connection()
        conn.execute('VACUUM')
        conn.execute('ANALYZE')
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/db/stats')
def api_db_stats():
    """Статистика БД"""
    stats = get_db_stats()
    return jsonify(stats)


@web_bp.route('/api/license/<int:license_id>/refresh', methods=['POST'])
def api_refresh_license(license_id):
    """Обновить данные лицензии из файла"""
    lic = get_license_by_id(license_id)
    if not lic:
        return jsonify({'success': False, 'message': 'Лицензия не найдена'}), 404
    
    try:
        from modules.parsers import parse_license_file
        from modules.database import update_license
        
        result = parse_license_file(lic['local_path'])
        update_license(license_id, result)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/tags/<int:tag_id>', methods=['PUT'])
def api_update_tag(tag_id):
    """Обновить тег"""
    from modules.database import update_tag
    
    data = request.get_json()
    update_tag(tag_id, data.get('name'), data.get('color'))
    return jsonify({'success': True})


@web_bp.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    """Удалить тег"""
    from modules.database import delete_tag
    delete_tag(tag_id)
    return jsonify({'success': True})


@web_bp.route('/api/comments/<int:comment_id>', methods=['PUT'])
def api_update_comment(comment_id):
    """Обновить комментарий"""
    from modules.database import update_comment
    
    data = request.get_json()
    update_comment(comment_id, data.get('text'))
    return jsonify({'success': True})


@web_bp.route('/<operator>/export')
def export_page(operator):
    """Страница экспорта"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    from modules.database import get_dynamic_columns
    dynamic_columns = get_dynamic_columns()
    
    return render_template('export.html',
                          dynamic_columns=dynamic_columns,
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


# ========== ФИНАЛЬНЫЕ ДОПОЛНЕНИЯ ==========

@web_bp.route('/api/capacity_mapping/bulk', methods=['POST'])
def api_bulk_capacity_mapping():
    """Массовое добавление соответствий"""
    from modules.capacity_mapper import add_mapping
    
    data = request.get_json()
    items = data.get('items', [])
    
    added = 0
    for item in items:
        try:
            add_mapping(
                item['capacity_key'],
                item['spart'],
                item['bpart'],
                item.get('operator')
            )
            added += 1
        except:
            pass
    
    return jsonify({'success': True, 'added': added})


@web_bp.route('/api/license/<int:license_id>/download')
def api_download_license(license_id):
    """Скачать файл лицензии"""
    from flask import send_file
    
    lic = get_license_by_id(license_id)
    if not lic or not lic.get('local_path'):
        return jsonify({'success': False, 'message': 'Файл не найден'}), 404
    
    path = lic['local_path']
    if not os.path.exists(path):
        return jsonify({'success': False, 'message': 'Файл не существует'}), 404
    
    return send_file(path, as_attachment=True)


@web_bp.route('/api/backup/<path:filename>', methods=['DELETE'])
def api_delete_backup(filename):
    """Удалить бэкап"""
    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    path = os.path.join(backup_dir, os.path.basename(filename))
    
    if os.path.exists(path) and path.endswith('.db'):
        os.remove(path)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Бэкап не найден'}), 404


@web_bp.route('/api/logs')
def api_get_logs():
    """Получить последние строки лога"""
    lines = request.args.get('lines', 100, type=int)
    log_file = current_app.config.get('LOG_FILE', 'logs/app.log')
    
    if not os.path.exists(log_file):
        return jsonify({'lines': []})
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()
    
    return jsonify({'lines': all_lines[-lines:]})


@web_bp.route('/api/settings/reset', methods=['POST'])
def api_reset_settings():
    """Сброс настроек к значениям по умолчанию"""
    from modules.config_store import reset_to_defaults
    reset_to_defaults()
    return jsonify({'success': True})


@web_bp.route('/<operator>/api/licenses_data')
def api_licenses_data(operator):
    """API для получения данных лицензий (для AJAX)"""
    # Параметры
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    filters = {}
    for key in ['esn', 'ne_type', 'city', 'site', 'year', 'domain', 'tag', 'search']:
        value = request.args.get(key, '').strip()
        if value:
            filters[key] = value
    
    result = get_licenses(operator, filters=filters, page=page, per_page=per_page)
    return jsonify(result)


@web_bp.route('/<operator>/api/resources_data')
def api_resources_data(operator):
    """API для получения ресурсов"""
    license_id = request.args.get('license_id', type=int)
    if not license_id:
        return jsonify([])
    
    from modules.capacity_mapper import get_grouped_resources
    resources = get_grouped_resources(license_id=license_id, operator=operator)
    return jsonify(resources)




# ========== УТИЛИТЫ ДЛЯ НОВЫХ МАРШРУТОВ ==========

# ========== TARGETS MAPPING (Excel) ==========

@web_bp.route('/<operator>/targets_mapping')
def targets_mapping(operator):
    """Страница маппинга Targets"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    return render_template('targets_mapping.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator))


@web_bp.route('/<operator>/targets_mapping/preview', methods=['POST'])
def targets_mapping_preview(operator):
    """Предпросмотр загрузки Targets Excel"""
    from modules.targets_mapper import preview_targets
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        file.save(tmp.name)
        result = preview_targets(operator, tmp.name)
        os.unlink(tmp.name)
    
    return jsonify(result)


@web_bp.route('/<operator>/targets_mapping/load', methods=['POST'])
def targets_mapping_load(operator):
    """Загрузка Targets из Excel"""
    from modules.targets_mapper import load_targets
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        file.save(tmp.name)
        result = load_targets(operator, tmp.name)
        os.unlink(tmp.name)
    
    return jsonify(result)


@web_bp.route('/<operator>/targets_mapping/compute', methods=['POST'])
def targets_mapping_compute(operator):
    """Вычисление Targets"""
    from modules.targets_mapper import compute_targets
    
    data = request.get_json() or {}
    result = compute_targets(operator, data)
    return jsonify(result)


@web_bp.route('/<operator>/targets_mapping/data')
def targets_mapping_data(operator):
    """Получить данные Targets"""
    from modules.targets_mapper import get_targets_data
    
    tab = request.args.get('tab', 'targets')
    result = get_targets_data(operator, tab)
    return jsonify(result)


# ========== ESN MAPPING (Excel) ==========

@web_bp.route('/<operator>/esn_mapping/preview', methods=['POST'])
def esn_mapping_preview(operator):
    """Предпросмотр загрузки ESN Excel"""
    from modules.esn_mapper import preview_esn
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        file.save(tmp.name)
        result = preview_esn(operator, tmp.name)
        os.unlink(tmp.name)
    
    return jsonify(result)


@web_bp.route('/<operator>/esn_mapping/load', methods=['POST'])
def esn_mapping_load(operator):
    """Загрузка ESN из Excel"""
    from modules.esn_mapper import load_esn
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    file = request.files['file']
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        file.save(tmp.name)
        result = load_esn(operator, tmp.name)
        os.unlink(tmp.name)
    
    return jsonify(result)


@web_bp.route('/<operator>/esn_mapping/apply', methods=['POST'])
def esn_mapping_apply(operator):
    """Применение ESN маппинга"""
    from modules.esn_mapper import apply_esn_mapping
    
    result = apply_esn_mapping(operator)
    return jsonify(result)


@web_bp.route('/<operator>/esn_mapping/export')
def esn_mapping_export(operator):
    """Экспорт ESN маппинга"""
    from flask import send_file
    from modules.esn_mapper import export_esn_mapping
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        export_esn_mapping(operator, tmp.name)
        return send_file(tmp.name, as_attachment=True, 
                        download_name=f'esn_mapping_{operator}.xlsx')


# ========== ОБНОВЛЁННЫЕ МАРШРУТЫ НАСТРОЕК ==========

@web_bp.route('/api/settings/backup_db', methods=['POST'])
def api_settings_backup_db():
    """Создать бэкап БД"""
    path = backup_db()
    return jsonify({'success': True, 'path': path})


@web_bp.route('/api/settings/preview_reorganize', methods=['POST'])
def api_preview_reorganize():
    """Предпросмотр реорганизации"""
    from modules.renamer import preview_rename
    
    data = request.get_json() or {}
    operator = data.get('operator')
    
    if operator:
        result = preview_rename(operator)
    else:
        # Для всех операторов
        result = []
        for op in current_app.config.get('OPERATORS', []):
            result.extend(preview_rename(op['name']))
    
    return jsonify({'success': True, 'items': result})


@web_bp.route('/api/settings/apply_reorganize', methods=['POST'])
def api_apply_reorganize():
    """Применить реорганизацию"""
    from modules.renamer import apply_rename
    
    data = request.get_json() or {}
    operator = data.get('operator')
    items = data.get('items', [])
    
    result = apply_rename(operator, items)
    return jsonify(result)


@web_bp.route('/api/settings/clear_logs', methods=['POST'])
def api_settings_clear_logs():
    """Очистить логи"""
    try:
        log_dir = current_app.config.get('LOG_DIR', 'logs')
        cleared = 0
        for f in os.listdir(log_dir):
            if f.endswith('.log'):
                os.remove(os.path.join(log_dir, f))
                cleared += 1
        return jsonify({'success': True, 'cleared': cleared})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/settings/reset_db', methods=['POST'])
def api_settings_reset_db():
    """Сбросить БД"""
    try:
        db_path = current_app.config.get('DB_PATH', 'local_licenses.db')
        if os.path.exists(db_path):
            os.remove(db_path)
        
        from modules.database import init_db
        init_db()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@web_bp.route('/api/settings/run_tests', methods=['POST'])
def api_settings_run_tests():
    """Запустить тесты"""
    import subprocess
    
    data = request.get_json() or {}
    category = data.get('category', 'all')
    test_name = data.get('test')
    
    cmd = ['python', '-m', 'pytest', 'tests/', '-v', '--tb=short']
    if category != 'all':
        cmd = ['python', '-m', 'pytest', f'tests/test_{category}.py', '-v', '--tb=short']
    if test_name:
        cmd.extend(['-k', test_name])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr,
            'returncode': result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'output': 'Тесты превысили лимит времени (5 минут)'})
    except Exception as e:
        return jsonify({'success': False, 'output': str(e)})


# ========== ВОССТАНОВЛЕНИЕ ИЗ БЭКАПА ==========

@web_bp.route('/settings/restore_backup')
def restore_backup():
    """Восстановление БД из бэкапа"""
    filename = request.args.get('file', '')
    if not filename or os.path.basename(filename) != filename or not filename.endswith('.db'):
        return jsonify({'success': False, 'message': 'Некорректное имя файла бэкапа'}), 400

    backup_dir = current_app.config.get('BACKUP_DIR', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    if not os.path.exists(backup_path):
        flash('Бэкап не найден', 'error')
        return redirect(url_for('web.settings'))
    
    try:
        db_path = current_app.config.get('DB_PATH', 'local_licenses.db')
        shutil.copy2(backup_path, db_path)
        flash(f'БД восстановлена из {filename}', 'success')
    except Exception as e:
        flash(f'Ошибка восстановления: {e}', 'error')
    
    return redirect(url_for('web.settings'))





# ========== SPart-дерево и Sharing ==========

@web_bp.route('/api/license/<int:license_id>/spart_tree')
def api_license_spart_tree(license_id):
    """Дерево ресурсов SPart/BPart для лицензии"""
    from modules.capacity_mapper import (
        load_targets_from_excel, load_sharing_from_excel,
        compute_license_targets, load_full_capacity_list,
        get_description_file_and_sheet
    )
    
    lic = get_license_by_id(license_id)
    if not lic:
        return jsonify({'error': 'Лицензия не найдена'}), 404
    
    operator = lic.get('operator', '')
    ne_type = lic.get('ne_type', '')
    show_all = request.args.get('show_all', '0') == '1'
    
    targets_file = current_app.config.get('targets_file', '')
    network_storage = current_app.config.get('network_storage_path', '')
    
    if not targets_file or not os.path.exists(targets_file):
        # Fallback: просто ресурсы без дерева
        resources = get_resources(license_id)
        items = []
        for r in resources:
            items.append({
                'name': r['capacity_key'],
                'value': r['value'],
                'valid_date': r.get('valid_date', ''),
                'part_number': r.get('part_number', ''),
                'dimension': r.get('dimension', ''),
                'description': r.get('description', ''),
                'is_empty': False,
                'target_value': '',
                'type': 'bpart',
                'is_bpart': True,
                'children': []
            })
        return jsonify({'sparts': items, 'orphans': []})
    
    # Загружаем данные
    targets = load_targets_from_excel(targets_file)
    sharing_map = load_sharing_from_excel(targets_file)
    
    mapping_info = get_description_file_and_sheet(ne_type)
    domain = mapping_info.get('domain', '') if mapping_info else ''
    
    full_list = load_full_capacity_list(domain, network_storage, ne_type, operator)
    
    if not full_list:
        resources = get_resources(license_id)
        items = []
        for r in resources:
            items.append({
                'name': r['capacity_key'],
                'value': r['value'],
                'valid_date': r.get('valid_date', ''),
                'part_number': r.get('part_number', ''),
                'dimension': r.get('dimension', ''),
                'description': r.get('description', ''),
                'is_empty': False,
                'target_value': '',
                'type': 'bpart',
                'is_bpart': True,
                'children': []
            })
        return jsonify({'sparts': items, 'orphans': []})
    
    for item in full_list:
        item['ne_type'] = ne_type
    
    # Значения из БД
    resources = get_resources(license_id)
    values_map = {r['capacity_key']: r['value'] for r in resources}
    date_map = {r['capacity_key']: r.get('valid_date', '') for r in resources}
    
    # Targets map
    targets_map = {}
    for (op, key), info in targets.items():
        if op != operator:
            continue
        city = lic.get('city', '')
        city_values = info.get('city_values', {})
        if city in city_values:
            targets_map[key] = city_values[city]
        elif 'ALL' in city_values:
            targets_map[key] = city_values['ALL']
        elif city_values:
            targets_map[key] = list(city_values.values())[0]
    
    def evaluate_target(formula_str, spart_target=None):
        """Вычисляет целевое значение по формуле."""
        if not formula_str:
            return ''
        expr = str(formula_str).strip()
        
        # Если есть targets_map с этим ключом
        if expr in targets_map:
            return targets_map[expr]
        
        # Заменяем ссылки на переменные
        def replace_var(m):
            var_name = m.group(0)
            if var_name in targets_map:
                return str(targets_map[var_name])
            return '0'
        
        expr_eval = re.sub(r'[A-Za-z_]\w*', replace_var, expr)
        
        try:
            result = eval(expr_eval, {'__builtins__': {}}, {})
            return result
        except:
            return ''
    
    def roundup(value, digits=0):
        import math
        multiplier = 10 ** digits
        return math.ceil(value * multiplier) / multiplier
    
    # ========== 7. СЦЕНАРИЙ 1: ИЕРАРХИЧЕСКИЙ ==========
    has_spart = any(item.get('type') == 'spart' for item in full_list)
    
    if has_spart:
        sparts_dict = {}
        
        for item in full_list:
            if item.get('type') == 'spart':
                spart_name = item['name']
                sparts_dict[spart_name] = {
                    'name': spart_name,
                    'value': 0,
                    'valid_date': '',
                    'part_number': item.get('part_number', ''),
                    'dimension': item.get('dimension', ''),
                    'description': item.get('description', ''),
                    'is_empty': True,
                    'target_value': '',
                    'sort_order': item.get('sort_order', 9999),
                    'spart_coeff': item.get('spart_coeff'),
                    'main_bpart': item.get('main_bpart'),
                    'type': 'spart',
                    'children': []
                }
        
        # BPart к SPart
        for item in full_list:
            if item.get('type') == 'bpart':
                spart_name = item.get('spart', '')
                if spart_name in sparts_dict:
                    sparts_dict[spart_name]['children'].append({
                        'name': item['name'],
                        'value': 0,
                        'valid_date': '',
                        'part_number': item.get('part_number', ''),
                        'dimension': item.get('dimension', ''),
                        'description': item.get('description', ''),
                        'formula': item.get('formula'),
                        'is_empty': True,
                        'target_value': '',
                        'sort_order': item.get('sort_order', 9999),
                        'type': 'bpart',
                        'is_bpart': True
                    })
        
        for spart in sparts_dict.values():
            spart['children'].sort(key=lambda x: x.get('sort_order', 9999))

        # Значения BPart
        for spart in sparts_dict.values():
            for child in spart['children']:
                if child['name'] in values_map:
                    child['value'] = values_map[child['name']]
                    child['valid_date'] = date_map.get(child['name'], '')
                    child['is_empty'] = False

        # Значения SPart
        for spart in sparts_dict.values():
            main_bpart = spart.get('main_bpart')
            if main_bpart and main_bpart in values_map:
                spart['value'] = values_map[main_bpart]
                spart['valid_date'] = date_map.get(main_bpart, '')
                spart['is_empty'] = False
            elif spart['children']:
                total = sum(c.get('value', 0) for c in spart['children'])
                if total > 0:
                    spart['value'] = total
                    spart['is_empty'] = False

            # Коэффициент
            if spart.get('spart_coeff') and spart['value'] > 0:
                try:
                    spart['value'] = roundup(spart['value'] * float(spart['spart_coeff']), 0)
                except (ValueError, TypeError):
                    pass

            # Цель SPart
            spart['target_value'] = targets_map.get(spart['name'], '')

            # Цели BPart
            for child in spart['children']:
                child_formula = child.get('formula')
                if child_formula:
                    child['target_value'] = evaluate_target(
                        child_formula,
                        spart['target_value'] if spart['target_value'] else None
                    )
                else:
                    child['target_value'] = targets_map.get(child['name'], '')

        # Фильтрация
        if not show_all:
            filtered = {}
            for name, spart in sparts_dict.items():
                has_value = spart.get('value', 0) > 0
                has_target = (spart.get('target_value') is not None
                              and spart.get('target_value') != ''
                              and spart.get('target_value') != 0)

                # ========== ГЛАВНОЕ ПРАВИЛО ==========
                # SPart показываем только если:
                #  - есть цель (has_target)
                #  - ИЛИ есть собственное значение > 0 (has_value)
                # Дети без цели родителя не показываются
                if not has_target:
                    if has_value:
                        filtered[name] = spart
                    continue

                filtered[name] = spart
            sparts_dict = filtered

        sorted_sparts = sorted(sparts_dict.values(), key=lambda x: x.get('sort_order', 9999))

        return jsonify({
            'sparts': sorted_sparts,
            'orphans': []
        })

    # ========== 8. СЦЕНАРИЙ 2: ПЛОСКИЙ ==========
    else:
        sections = []
        items = []

        for item in full_list:
            item_type = item.get('type', '')
            sort_order = item.get('sort_order', 9999)

            if item_type == 'section':
                sections.append({'name': item['name'], 'position': sort_order})
            elif item_type == 'bpart':
                items.append({
                    'name': item['name'], 'value': 0, 'valid_date': '',
                    'part_number': item.get('part_number', ''),
                    'dimension': item.get('dimension', ''),
                    'description': item.get('description', ''),
                    'formula': item.get('formula'),
                    'is_empty': True, 'target_value': '',
                    'sort_order': sort_order,
                    'type': 'bpart', 'is_bpart': True, 'children': []
                })
            elif item_type == 'variable':
                items.append({
                    'name': item['name'], 'value': 0, 'valid_date': '',
                    'part_number': '', 'dimension': item.get('dimension', ''),
                    'description': item.get('description', ''),
                    'formula': item.get('formula'),
                    'is_empty': True, 'target_value': '',
                    'sort_order': sort_order,
                    'type': 'variable', 'is_variable': True, 'children': []
                })

        # Значения из БД
        for item in items:
            if item['name'] in values_map:
                item['value'] = values_map[item['name']]
                item['valid_date'] = date_map.get(item['name'], '')
                item['is_empty'] = False

        # Переменные
        for item in items:
            if item.get('type') != 'variable':
                continue

            if item['name'] in targets_map:
                item['value'] = targets_map[item['name']]
                item['is_empty'] = False
                continue

            formula = item.get('formula', '')
            if not formula:
                continue

            # Регистронезависимая ссылка
            if formula in targets_map:
                item['value'] = targets_map[formula]
                item['is_empty'] = False
            else:
                for k in targets_map.keys():
                    if k.lower() == formula.lower():
                        item['value'] = targets_map[k]
                        item['is_empty'] = False
                        break

        # Цели BPart
        for item in items:
            if item.get('type') != 'bpart':
                continue
            formula = item.get('formula', '')
            if not formula:
                item['target_value'] = ''
                continue
            item['target_value'] = evaluate_target(str(formula).strip(), None)

        # Цели переменных
        for item in items:
            if item.get('type') == 'variable':
                item['target_value'] = targets_map.get(item['name'], '')

        # Формируем результат с секциями
        result_items = []
        sections.sort(key=lambda x: x['position'])
        items.sort(key=lambda x: x.get('sort_order', 9999))

        for section in sections:
            result_items.append({
                'name': section['name'], 'is_section': True,
                'value': '', 'valid_date': '', 'children': [],
                'target_value': '', 'sort_order': section['position']
            })

            next_pos = None
            for s in sections:
                if s['position'] > section['position']:
                    next_pos = s['position']
                    break

            section_items = []
            for item in items[:]:
                if next_pos is None:
                    if item.get('sort_order', 9999) > section['position']:
                        section_items.append(item)
                        items.remove(item)
                else:
                    if section['position'] < item.get('sort_order', 9999) < next_pos:
                        section_items.append(item)
                        items.remove(item)

            section_items.sort(key=lambda x: x.get('sort_order', 9999))
            result_items.extend(section_items)

        items.sort(key=lambda x: x.get('sort_order', 9999))
        result_items.extend(items)

        # Фильтрация
        if not show_all:
            filtered = []
            for item in result_items:
                if item.get('is_section'):
                    filtered.append(item)
                    continue
                if item.get('type') == 'variable' or item.get('is_variable'):
                    continue
                has_value = item.get('value', 0) > 0
                has_target = (item.get('target_value') is not None
                              and item.get('target_value') != ''
                              and item.get('target_value') != 0)
                if has_value or has_target:
                    filtered.append(item)
            result_items = filtered

        return jsonify({
            'sparts': result_items,
            'orphans': []
        })
        
@web_bp.route('/<operator>/refresh_targets', methods=['POST'])
def refresh_targets(operator):
    """Пересчитать цели для оператора"""
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'success': False, 'message': 'Оператор не найден'}), 404
    
    network_storage_path = current_app.config.get('network_storage_path', '')
    if not network_storage_path:
        return jsonify({'success': False, 'message': 'Не указан путь к сетевому хранилищу'}), 400
    
    try:
        from modules.database import refresh_all_targets
        count = refresh_all_targets(operator, network_storage_path)
        return jsonify({
            'success': True, 
            'message': f'Пересчитано {count} целевых значений',
            'count': count
        })
    except Exception as e:
        logger.error(f"Ошибка пересчёта целей: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
          
@web_bp.route('/api/check_esn_mapping_files', methods=['GET'])
def api_check_esn_mapping_files():
    """Проверяет наличие файлов ESN маппинга для всех операторов"""
    import os
    from flask import current_app
    
    mapping_path = current_app.config.get('mapping_path', '//A00742028-C5NC5/_Licenses/mapping')
    operators = current_app.config.get('OPERATORS', [])
    
    files = []
    for op in operators:
        mapping_file = op.get('mapping_file', f"{op.get('name')}_esn_mapping.xlsx")
        file_path = os.path.join(mapping_path, mapping_file)
        files.append({
            'name': mapping_file,
            'path': file_path,
            'exists': os.path.exists(file_path)
        })
    
    missing_count = sum(1 for f in files if not f['exists'])
    
    return jsonify({
        'success': True,
        'mapping_path': mapping_path,
        'files': files,
        'missing_count': missing_count,
        'total_count': len(files)
    })

@web_bp.route('/api/check_license_details_files', methods=['GET'])
def api_check_license_details_files():
    """Проверяет наличие файлов описаний CapacityKey для всех NE типов"""
    import os
    from flask import current_app
    
    details_path = current_app.config.get('license_details_path', '//A00742028-C5NC5/_Licenses/license_details')
    
    # Получаем уникальные NE типы из БД
    from modules.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT ne_type FROM licenses WHERE ne_type IS NOT NULL AND ne_type != ""')
    ne_types = [r[0] for r in cursor.fetchall()]
    conn.close()
    
    files = []
    for ne_type in ne_types:
        file_name = f"{ne_type}_license_details.xlsx"
        file_path = os.path.join(details_path, file_name)
        files.append({
            'name': file_name,
            'path': file_path,
            'exists': os.path.exists(file_path)
        })
    
    # Добавляем общие файлы
    common_files = ['PS_license_details.xlsx', 'vEPC_license_details.xlsx']
    for common_file in common_files:
        file_path = os.path.join(details_path, common_file)
        files.append({
            'name': common_file,
            'path': file_path,
            'exists': os.path.exists(file_path)
        })
    
    missing_count = sum(1 for f in files if not f['exists'])
    
    return jsonify({
        'success': True,
        'details_path': details_path,
        'files': files,
        'missing_count': missing_count,
        'total_count': len(files)
    })
    
@web_bp.route('/api/open_folder')
def api_open_folder():
    """Открыть папку с файлом лицензии (сначала на сервере, потом локально)"""
    import subprocess
    import urllib.parse
    
    license_id = request.args.get('license_id', type=int)
    if not license_id:
        return jsonify({'success': False, 'error': 'Не указан license_id'})
    
    # Получаем данные лицензии
    lic = get_license_by_id(license_id)
    if not lic:
        return jsonify({'success': False, 'error': 'Лицензия не найдена'})
    
    network_storage = current_app.config.get('network_storage_path', '')
    
    # Пытаемся построить сетевой путь
    if network_storage and lic.get('domain') and lic.get('city'):
        # Определяем год как в sync_manager
        valid_date = lic.get('valid_date', '')
        year_folder = lic.get('year', 'permanent')
        if valid_date and valid_date not in ('PERMANENT', 'UNKNOWN'):
            try:
                import re
                date_match = re.match(r'(\d{4})-(\d{2})', valid_date)
                if date_match:
                    year = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year_folder = str(year - 1) if month <= 3 else str(year)
            except:
                pass
        
        # Генерируем имя файла как в sync_manager
        version = lic.get('version', '')
        version_short = version
        if version:
            r_match = re.search(r'R(\d+)', version, re.IGNORECASE)
            if r_match:
                version_short = 'R' + str(int(r_match.group(1)))
        
        filename = f"LIC{lic.get('ne_type', '')}_{version_short}_{lic.get('city', '')}_{lic.get('site', '')}_{year_folder}.dat"
        filename = re.sub(r'[^\w\-.]', '_', filename)
        
        remote_dir = os.path.join(network_storage, lic.get('operator', ''), lic.get('domain', ''), lic.get('city', ''), year_folder)
        remote_path = os.path.join(remote_dir, filename)
        
        # Если сетевая папка существует — открываем её
        if os.path.exists(remote_dir):
            try:
                subprocess.Popen(['explorer', '/select,', os.path.normpath(remote_path)])
                return jsonify({'success': True, 'path': remote_path, 'source': 'network'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
    
    # Если сетевой путь не найден — пробуем локальный
    local_path = lic.get('local_path')
    if local_path and os.path.exists(local_path):
        try:
            local_dir = os.path.dirname(local_path)
            subprocess.Popen(['explorer', os.path.normpath(local_dir)])
            return jsonify({'success': True, 'path': local_path, 'source': 'local'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Файл не найден ни на сервере, ни локально'})
       
@web_bp.route('/api/license/<int:license_id>/info')
def api_get_license_info(license_id):
    """Получить базовую информацию о лицензии"""
    license_data = get_license_by_id(license_id)
    if not license_data:
        return jsonify({'error': 'Not found'}), 404
    
    return jsonify({
        'id': license_data['id'],
        'esn': license_data.get('esn'),
        'lsn': license_data.get('lsn'),
        'product': license_data.get('product'),
        'version': license_data.get('version'),
        'ne_type': license_data.get('ne_type'),
        'city': license_data.get('city'),
        'site': license_data.get('site'),
        'year': license_data.get('year'),
        'valid_date': license_data.get('valid_date'),
        'create_time': license_data.get('create_time'),
        'node': license_data.get('node'),
        'domain': license_data.get('domain'),
        'filename': license_data.get('filename'),
        'operator': license_data.get('operator'),
        'local_path': license_data.get('local_path'),  # ← ДОБАВИТЬ
        'file_hash': license_data.get('file_hash')     # ← ДОБАВИТЬ (для синхронизации)
    })
    
@web_bp.route('/api/license_versions')
def api_get_license_versions():
    """Получить все версии для ESN"""
    operator = request.args.get('operator')
    esn = request.args.get('esn')
    if not operator or not esn:
        return jsonify({'error': 'operator and esn required'}), 400
    
    licenses = get_all_licenses_for_esn(operator, esn)
    
    # Добавляем local_path к каждой версии
    for lic in licenses:
        full = get_license_by_id(lic['id'])
        if full:
            lic['local_path'] = full.get('local_path')
    
    return jsonify(licenses)
  
@web_bp.route('/<operator>/license_by_esn/<esn>')
def license_detail_by_esn(operator, esn):
    """Детальная страница для ESN со всеми LSN"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    licenses = get_all_licenses_for_esn(operator, esn)
    
    if not licenses:
        abort(404)
    
    # Получаем данные первой лицензии
    main_license = get_license_by_id(licenses[0]['id'])
    
    # Получаем домен и обогащаем ресурсы
    domain = main_license.get('domain')
    if not domain:
        # Если нет в main_license, получи из БД напрямую
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('SELECT domain FROM licenses WHERE id = ?', (licenses[0]['id'],))
        row = cur.fetchone()
        domain = row[0] if row else ''
        conn.close()
    network_storage_path = current_app.config.get('network_storage_path', '')
    
    from modules.license_service import LicenseService
    main_license = LicenseService.enrich_resources_with_descriptions(
        main_license, domain, network_storage_path
    )
    
    # Добавляем теги, комментарии, динамические поля
    main_license['tags'] = get_license_tags(main_license.get('id'))
    main_license['comments'] = get_comments(main_license.get('id'))
    main_license['dynamic_values'] = get_dynamic_values_for_license(main_license['id'])
    
    # Для списка версий тоже обогащаем ресурсы (для предпросмотра)
    all_licenses_data = []
    for lic in licenses:
        full_lic = get_license_by_id(lic['id'])
        if full_lic:
            full_lic = LicenseService.enrich_resources_with_descriptions(
                full_lic, domain, network_storage_path
            )
            all_licenses_data.append(full_lic)
        else:
            all_licenses_data.append(lic)

    return render_template('license_detail.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator),
                          license=main_license,
                          all_licenses_for_esn=all_licenses_data,
                          esn=esn,
                          network_storage_path=network_storage_path,
                          domain=domain)

@web_bp.route('/<operator>/license_by_esns')
def license_detail_by_esns(operator):
    """Детали лицензии с возможностью переключения между ESN"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)

    esns_param = request.args.get('esns', '')
    esn_list = list(dict.fromkeys([e.strip() for e in esns_param.split(',') if e.strip()]))

    if not esn_list:
        abort(400, description="Не указаны ESN")

    # Получаем первую лицензию для каждого ESN (одна запись на ESN)
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(esn_list))
    cursor.execute(f'''
        SELECT l.esn, l.ne_type, l.city, l.site, l.domain, l.id
        FROM licenses l
        WHERE l.operator = ? AND l.esn IN ({placeholders})
        AND l.id = (
            SELECT l2.id FROM licenses l2 
            WHERE l2.esn = l.esn AND l2.operator = l.operator
            ORDER BY l2.create_time DESC LIMIT 1
        )
        ORDER BY l.ne_type, l.city, l.esn
    ''', [operator] + esn_list)
    esn_info = cursor.fetchall()
    conn.close()

    # Строим список уникальных ESN
    selected_esns = []
    seen_esns = set()
    for row in esn_info:
        esn = row[0]
        if esn not in seen_esns:
            seen_esns.add(esn)
            selected_esns.append({
                'esn': esn,
                'ne_type': row[1] or '',
                'city': row[2] or '',
                'site': row[3] or '',
                'domain': row[4] or '',
                'license_id': row[5]
            })

    if not selected_esns:
        abort(404, description="Лицензии не найдены")

    # Берём ID из параметра или первую лицензию
    first_license_id = request.args.get('license_id', type=int) or selected_esns[0]['license_id']
    valid_ids = [e['license_id'] for e in selected_esns]
    if first_license_id not in valid_ids:
        first_license_id = selected_esns[0]['license_id']

    # ===== ВАЖНО: Получаем domain из БД как в license_detail_by_esn =====
    main_license = get_license_by_id(first_license_id)
    if not main_license:
        abort(404)

    # Получаем домен — сначала из license_data, потом из БД
    domain = main_license.get('domain')
    if not domain:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('SELECT domain FROM licenses WHERE id = ?', (first_license_id,))
        row = cur.fetchone()
        domain = row[0] if row else ''
        conn.close()

    network_storage_path = current_app.config.get('network_storage_path', '')

    # Обогащаем ресурсы
    from modules.license_service import LicenseService
    main_license = LicenseService.enrich_resources_with_descriptions(
        main_license, domain, network_storage_path
    )

    main_license['tags'] = get_license_tags(first_license_id)
    main_license['comments'] = get_comments(first_license_id)
    main_license['dynamic_values'] = get_dynamic_values_for_license(first_license_id)

    # Получаем все версии для выбранного ESN
    current_esn = main_license.get('esn', esn_list[0])
    all_licenses_for_esn = get_all_licenses_for_esn(operator, current_esn)

    return render_template('license_detail.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator),
                          license=main_license,
                          all_licenses_for_esn=all_licenses_for_esn,
                          esn=current_esn,
                          domain=domain,
                          selected_esns=selected_esns)

# ========== РЕЗЕРВНОЕ КОПИРОВАНИЕ ==========

@web_bp.route('/backup_db', methods=['POST'])
def backup_database_route():
    backup_path = backup_db('all')
    if backup_path:
        return jsonify({'success': True, 'message': f'Бэкап создан: {backup_path}'})
    return jsonify({'success': False, 'message': 'Ошибка создания бэкапа'}), 500


# ========== ЭКСПОРТ В EXCEL ==========

@web_bp.route('/api/export/<operator>', methods=['POST'])
def api_export_to_excel(operator):
    """Экспорт лицензий в Excel"""
    import io
    from modules.database import get_all_licenses_for_export
    
    data = request.get_json()
    license_ids = data.get('license_ids', [])  # Если пусто - экспортируем все
    visible_columns = data.get('visible_columns', [])
    
    # Получаем данные
    licenses = get_all_licenses_for_export(operator, license_ids if license_ids else None)
    
    if not licenses:
        return jsonify({'error': 'Нет данных для экспорта'}), 400
    
    # Формируем заголовки
    headers = []
    col_map = []
    
    column_names = {
        'ne_type': 'NE тип',
        'city': 'Город',
        'site': 'Сайт',
        'year': 'Год',
        'lsn': 'LSN',
        'product': 'Продукт',
        'version': 'Версия',
        'esn': 'ESN',
        'domain': 'Домен',
        'create_time': 'Дата создания',
        'valid_date': 'Действует до',
        'tags_agg': 'Теги',
        'comments_count': 'Комментарии'
    }
    
    for col in visible_columns:
        if col in column_names:
            headers.append(column_names[col])
            col_map.append(col)
        elif col.startswith('dynamic_'):
            # Динамическое поле
            dyn_col = col.replace('dynamic_', '')
            headers.append(dyn_col)
            col_map.append(f'dynamic_{dyn_col}')
    
    # Создаём Excel
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Лицензии {operator}"
    
    # Заголовки
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E60012", end_color="E60012", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    
    # Данные
    for row_idx, lic in enumerate(licenses, 2):
        for col_idx, col_name in enumerate(col_map, 1):
            if col_name.startswith('dynamic_'):
                dyn_name = col_name.replace('dynamic_', '')
                value = lic.get('dynamic_values', {}).get(dyn_name, '')
            else:
                value = lic.get(col_name, '')
            
            if col_name == 'comments_count':
                value = f'💬 {value}' if value else ''
            
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(horizontal="left")
    
    # Авто-ширина
    for col_idx, _ in enumerate(headers, 1):
        max_length = 0
        column = ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)]
        for row_idx in range(1, len(licenses) + 2):
            cell_value = ws.cell(row=row_idx, column=col_idx).value
            if cell_value:
                max_length = max(max_length, len(str(cell_value)))
        column.width = min(max_length + 2, 50)
    
    # Сохраняем в буфер
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    # Отправляем файл
    from flask import send_file
    filename = f'licenses_{operator}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ========== ПРЕДУСТАНОВКИ ФИЛЬТРОВ (API для синхронизации с localStorage) ==========

@web_bp.route('/api/presets', methods=['GET'])
def api_get_presets():
    """Получить сохранённые предустановки из localStorage (через запрос)"""
    # Предустановки хранятся в localStorage на клиенте
    # Этот эндпоинт нужен для импорта/экспорта через сервер
    return jsonify({'message': 'Используйте localStorage на клиенте'})


# ========== УМНЫЙ ПОИСК ==========

@web_bp.route('/api/smart_search/<operator>', methods=['POST'])
def api_smart_search(operator):
    """Умный поиск по лицензиям"""
    from modules.database import get_connection
    
    query = request.get_json().get('query', '')
    if not query:
        return jsonify({'results': [], 'suggestions': []})
    
    conn = get_connection()
    cursor = conn.cursor()
    
    suggestions = []
    
    # Поиск CapacityKey
    if any(c.isalpha() for c in query):
        cursor.execute('''
            SELECT DISTINCT capacity_key 
            FROM resources 
            WHERE capacity_key LIKE ? 
            LIMIT 10
        ''', (f'%{query.upper()}%',))
        capacity_keys = [r[0] for r in cursor.fetchall()]
        for key in capacity_keys:
            suggestions.append({
                'text': key,
                'type': 'capacity_key',
                'description': f'CapacityKey: {key}'
            })
    
    # Поиск тегов
    cursor.execute('SELECT name FROM tags WHERE name LIKE ? LIMIT 5', (f'%{query}%',))
    tags = [r[0] for r in cursor.fetchall()]
    for tag in tags:
        suggestions.append({
            'text': f'tag:{tag}',
            'type': 'tag',
            'description': f'Тег: {tag}'
        })
    
    conn.close()
    
    # Команды (подсказки)
    commands = [
        {'text': 'expiring:30', 'type': 'command', 'description': 'Истекает через 30 дней'},
        {'text': 'expiring:60', 'type': 'command', 'description': 'Истекает через 60 дней'},
        {'text': 'permanent', 'type': 'command', 'description': 'Бессрочные лицензии'},
        {'text': 'city:', 'type': 'command', 'description': 'Фильтр по городу (city:Москва)'},
        {'text': 'site:', 'type': 'command', 'description': 'Фильтр по сайту (site:А101)'}
    ]
    
    for cmd in commands:
        if cmd['text'].startswith(query.lower()) or query in cmd['text']:
            suggestions.append(cmd)
    
    return jsonify({'suggestions': suggestions[:10]})


# Добавьте в конец файла modules/web/routes.py

# ========== МАССОВЫЕ ОПЕРАЦИИ С ТЕГАМИ ==========

@web_bp.route('/api/bulk_add_tag', methods=['POST'])
def api_bulk_add_tag():
    """Массовое добавление тега к лицензиям"""
    from modules.database import add_tag, add_tag_to_license, get_connection
    
    data = request.get_json()
    license_ids = data.get('license_ids', [])
    tag_name = data.get('tag_name', '').strip()
    
    if not license_ids:
        return jsonify({'error': 'Нет выбранных лицензий'}), 400
    
    if not tag_name:
        return jsonify({'error': 'Не указан тег'}), 400
    
    # Создаём тег (если не существует)
    tag_id = add_tag(tag_name)
    
    # Добавляем тег к каждой лицензии
    added = 0
    for lic_id in license_ids:
        try:
            add_tag_to_license(int(lic_id), tag_id)
            added += 1
        except Exception as e:
            pass
    
    return jsonify({
        'success': True,
        'added': added,
        'tag_name': tag_name,
        'message': f'Тег "{tag_name}" добавлен к {added} лицензиям'
    })


@web_bp.route('/api/bulk_remove_tag', methods=['POST'])
def api_bulk_remove_tag():
    """Массовое удаление тега с лицензий"""
    from modules.database import remove_tag_from_license, get_connection
    
    data = request.get_json()
    license_ids = data.get('license_ids', [])
    tag_id = data.get('tag_id')
    
    if not license_ids:
        return jsonify({'error': 'Нет выбранных лицензий'}), 400
    
    if not tag_id:
        return jsonify({'error': 'Не указан тег'}), 400
    
    removed = 0
    for lic_id in license_ids:
        try:
            remove_tag_from_license(int(lic_id), int(tag_id))
            removed += 1
        except Exception as e:
            pass
    
    return jsonify({
        'success': True,
        'removed': removed,
        'message': f'Тег удалён с {removed} лицензий'
    })


@web_bp.route('/api/all_tags', methods=['GET'])
def api_all_tags():
    """Получить все теги для массовых операций"""
    from modules.database import get_all_tags
    
    tags = get_all_tags()
    return jsonify(tags)

# ========== ДИНАМИЧЕСКИЕ ПОЛЯ ==========

@web_bp.route('/api/dynamic_columns', methods=['GET'])
def api_list_dynamic_columns():
    """Получить все динамические колонки"""
    from modules.database import get_dynamic_columns
    columns = get_dynamic_columns(active_only=False)
    return jsonify(columns)


@web_bp.route('/api/dynamic_columns', methods=['POST'])
def api_create_dynamic_column():
    """Добавить динамическую колонку"""
    from modules.database import add_dynamic_column, get_dynamic_columns
    
    data = request.get_json()
    column_name = data.get('column_name')
    display_name = data.get('display_name')
    rule_id = data.get('rule_id')
    capacity_key = data.get('capacity_key')
    aggregation_strategy = data.get('aggregation_strategy', 'sum')
    join_separator = data.get('join_separator', ', ')
    
    if not column_name or not display_name:
        return jsonify({'error': 'column_name и display_name обязательны'}), 400
    
    if not rule_id and not capacity_key:
        return jsonify({'error': 'Нужно указать rule_id или capacity_key'}), 400
    
    try:
        column_id = add_dynamic_column(column_name, display_name, rule_id, capacity_key, 
                                        aggregation_strategy, join_separator)
        
        return jsonify({
            'id': column_id,
            'message': f'Колонка добавлена'
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@web_bp.route('/api/dynamic_columns/<int:column_id>', methods=['PUT'])
def api_update_dynamic_column(column_id):
    """Обновить динамическую колонку"""
    from modules.database import update_dynamic_column
    data = request.get_json()
    update_dynamic_column(column_id, **data)
    return jsonify({'message': 'Колонка обновлена'})


@web_bp.route('/api/dynamic_columns/<int:column_id>', methods=['DELETE'])
def api_delete_dynamic_column(column_id):
    """Удалить динамическую колонку"""
    from modules.database import delete_dynamic_column
    delete_dynamic_column(column_id)
    return jsonify({'message': 'Колонка удалена'})


@web_bp.route('/api/extraction_rules', methods=['GET'])
def api_get_extraction_rules():
    """Получить банк правил"""
    rules = current_app.config.get('EXTRACTION_RULES', {'rules': {}})
    return jsonify(rules)


@web_bp.route('/api/extraction_rules', methods=['POST'])
def api_create_extraction_rule():
    """Добавить новое правило в банк"""
    import json
    import re
    import os
    from datetime import datetime
    
    data = request.get_json()
    rule_id = data.get('rule_id')
    display_name = data.get('display_name')
    regex_dat = data.get('regex_dat')
    xpath_xml = data.get('xpath_xml')
    value_type = data.get('value_type', 'text')
    aggregation_strategy = data.get('aggregation_strategy', 'first')
    join_separator = data.get('join_separator', ', ')
    
    if not rule_id or not display_name:
        return jsonify({'error': 'rule_id и display_name обязательны'}), 400
    
    # Валидация regex
    if regex_dat:
        try:
            pattern = regex_dat
            if pattern.startswith('r"') and pattern.endswith('"'):
                pattern = pattern[2:-1]
            elif pattern.startswith("r'") and pattern.endswith("'"):
                pattern = pattern[2:-1]
            re.compile(pattern)
        except re.error as e:
            return jsonify({'error': f'Невалидный regex: {e}'}), 400
    
    # Загружаем текущие правила
    rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'extraction_rules.json')
    
    with open(rules_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)
    
    # Добавляем правило
    rules['rules'][rule_id] = {
        'display_name': display_name,
        'regex_dat': regex_dat,
        'xpath_xml': xpath_xml,
        'value_type': value_type,
        'aggregation_strategy': aggregation_strategy,
        'join_separator': join_separator
    }
    rules['updated_at'] = datetime.now().isoformat()
    
    # Сохраняем
    with open(rules_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    
    # Обновляем конфиг приложения
    current_app.config['EXTRACTION_RULES'] = rules
    
    return jsonify({'message': f'Правило {rule_id} добавлено'})


@web_bp.route('/api/capacity_keys/<operator>', methods=['GET'])
def api_get_capacity_keys(operator):
    """Получить список CapacityKey для оператора"""
    from modules.scanner import get_available_capacity_keys
    keys = get_available_capacity_keys(operator)
    return jsonify(keys)


@web_bp.route('/<operator>/dynamic_fields')
def dynamic_fields_page(operator):
    """Страница управления динамическими полями"""
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)
    
    from modules.database import get_dynamic_columns
    columns = get_dynamic_columns(active_only=False)
    rules = current_app.config.get('EXTRACTION_RULES', {'rules': {}})
    
    return render_template('dynamic_fields.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator),
                          columns=columns,
                          rules=rules.get('rules', {}))
    
    
@web_bp.route('/<operator>/excel_mapping', methods=['GET', 'POST'])
def excel_mapping(operator):
    op_config = get_operator_config(operator)
    if not op_config:
        abort(404)

    from modules.capacity_mapper import (
        load_targets_from_excel, load_sharing_from_excel,
        compute_license_targets, load_full_capacity_list,
        get_description_file_and_sheet
    )
    from modules.database import get_connection

    targets_file = current_app.config.get('targets_file', '')
    network_storage = current_app.config.get('network_storage_path', '')

    message = ''

    # ========== POST-обработчики ==========
    if request.method == 'POST':
        action = request.form.get('action')

        # --- LOAD ---
        if action == 'load':
            targets = load_targets_from_excel(targets_file)
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM domain_targets')

            idx = 0
            for (op, target_key), info in targets.items():
                if op != operator:
                    continue
                group_name = info.get('group', '')
                domain = info.get('domain', '')
                unit = info.get('unit', '')
                for city, value in info['city_values'].items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO domain_targets
                        (operator, domain, type, unit, target_key, city, value, sharing, sort_order, group_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (op, domain, '', unit, target_key, city, value, None, idx, group_name))
                    idx += 1

            conn.commit()
            conn.close()
            message = f'✅ Загружено: {idx} целей'

        # --- COMPUTE ---
        elif action == 'compute':
            targets = load_targets_from_excel(targets_file)
            sharing_map = load_sharing_from_excel(targets_file)

            if not targets:
                message = "❌ Не удалось загрузить Targets"
            elif not sharing_map:
                message = "❌ Не удалось загрузить Sharing"
            else:
                # Все NE оператора (из licenses)
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT DISTINCT ne_type FROM licenses WHERE operator = ?',
                    (operator,)
                )
                ne_types = [r[0] for r in cursor.fetchall()]
                conn.close()

                # ========== Вспомогательная функция ==========
                def compute_for_ne(ne_type, extra_values=None):
                    """Расчёт для одного NE."""
                    mapping_info = get_description_file_and_sheet(ne_type)
                    domain = mapping_info.get('domain', '') if mapping_info else ''
                    if not domain:
                        return []
                    items = load_full_capacity_list(domain, network_storage, ne_type, operator)
                    if not items:
                        return []
                    for item in items:
                        item['ne_type'] = ne_type
                    return compute_license_targets(
                        targets, sharing_map, items, operator,
                        extra_values=extra_values
                    )

                # ========== Собираем группы NE (универсально) ==========
                # Группируем NE по share_group
                groups_ne = {}  # {group_name: [ne_types]}

                for (op, ne), info in sharing_map.items():
                    if op != operator:
                        continue
                    sg = info.get('share_group')
                    if sg:
                        groups_ne.setdefault(sg, []).append(ne)

                # Добавляем copy_from NE в группу источника
                for (op, ne), info in sharing_map.items():
                    if op != operator:
                        continue
                    src = info.get('copy_from')
                    if not src:
                        continue
                    # Найти группу, к которой относится src
                    src_group = None
                    for (op2, ne2), info2 in sharing_map.items():
                        if op2 == operator and ne2 == src:
                            src_group = info2.get('share_group')
                            break
                    if src_group:
                        if ne not in groups_ne.get(src_group, []):
                            groups_ne.setdefault(src_group, []).append(ne)

                # ========== Вычисляем значения по группам ==========
                group_values = {}  # {group_name: {(var, city): value}}

                for group_name, nes in groups_ne.items():
                    values = {}
                    for ne in nes:
                        for r in compute_for_ne(ne):
                            if r.get('item_type') == 'variable':
                                key = (r['capacity_key'], r['city'])
                                val = r['target_value']
                                # Берём max (не перезаписываем меньшим)
                                if key not in values or val > values[key]:
                                    values[key] = val
                    group_values[group_name] = values

                # ========== extra_values для всех групп ==========
                extra_values = group_values

                # ========== ПРОХОД: Все NE с extra_values ==========
                all_computed = []
                for ne_type in ne_types:
                    computed = compute_for_ne(ne_type, extra_values=extra_values)
                    all_computed.extend(computed)

                # ========== Сохраняем ==========
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM license_targets WHERE operator = ?', (operator,))
                for c in all_computed:
                    cursor.execute('''
                        INSERT INTO license_targets
                        (operator, target_key, city, ne_type, capacity_key, target_value, item_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (c['operator'], c['target_key'], c['city'], c['ne_type'],
                          c['capacity_key'], c['target_value'], c.get('item_type', 'target')))
                conn.commit()
                conn.close()

                # Отчёт
                groups_info = ', '.join(
                    f"{g}: {len(v)} значений" for g, v in group_values.items()
                )
                message = f'✅ Вычислено {len(all_computed)} целевых значений ({groups_info})'

    # ========== ЧТЕНИЕ ДЛЯ ОТОБРАЖЕНИЯ ==========
    conn = get_connection()
    cursor = conn.cursor()

    # 1. domain_targets
    cursor.execute('''
        SELECT * FROM domain_targets
        ORDER BY sort_order, target_key
    ''')
    domain_targets = [dict(zip(
        ['id','operator','domain','type','unit','target_key','city','value','sharing','sort_order','group_name'], r
    )) for r in cursor.fetchall()]

    # 2. license_targets
    cursor.execute('''
        SELECT id, operator, target_key, city, ne_type, capacity_key, target_value, item_type
        FROM license_targets
        ORDER BY ne_type, capacity_key
    ''')
    all_computed = [dict(zip(
        ['id','operator','target_key','city','ne_type','capacity_key','target_value','item_type'], r
    )) for r in cursor.fetchall()]

    # 3. ESN маппинг
    cursor.execute('SELECT esn, lsn, operator, domain, ne_type, city, site FROM esn_mapping')
    mappings = cursor.fetchall()
    conn.close()

    # ========== РАЗДЕЛЯЕМ computed ==========
    variable_targets = [c for c in all_computed if c.get('item_type') == 'variable']
    spart_targets = [
        c for c in all_computed
        if c.get('item_type') != 'variable'
        and c.get('capacity_key') != c.get('target_key')
    ]

    # Обогащаем domain
    for c in variable_targets + spart_targets:
        ne = c.get('ne_type', '')
        mapping_info = get_description_file_and_sheet(ne)
        c['domain'] = mapping_info.get('domain', 'Unknown') if mapping_info else 'Unknown'

    # ========== SHARING для отображения ==========
    from modules.capacity_mapper import load_sharing_from_excel
    sharing_data = load_sharing_from_excel(targets_file) if targets_file else {}

    # Функция нормализации домена (PS + vEPC → PS,vEPC)
    def normalize_domain(domain_str):
        if not domain_str:
            return 'Unknown'
        parts = {p.strip().lower() for p in domain_str.split(',') if p.strip()}
        # Если есть PS или vEPC — объединяем
        if 'ps' in parts or 'vepc' in parts:
            return 'PS,vEPC'
        # Иначе — первый (или как есть)
        return domain_str.strip()

    # Собираем все города из заголовков Sharing
    from modules.capacity_mapper import load_sharing_cities
    sharing_cities = load_sharing_cities(targets_file)

    # Группируем по НОРМАЛИЗОВАННОМУ домену
    sharing_groups = {}  # {domain_name: [items]}
    for (op, ne), info in sharing_data.items():
        if op != operator:
            continue
        domain_norm = normalize_domain(info.get('domain', ''))
        item = {
            'operator': op,
            'ne_type': ne,
            'domain': info.get('domain', ''),
            'share_group': info.get('share_group', '') or '—',
            'copy_from': info.get('copy_from', '') or '—',
            'sh': info.get('sh', {}),
        }
        sharing_groups.setdefault(domain_norm, []).append(item)

    # ESN-маппинг для новой вкладки
    from modules.config_store import get_esn_mapping_config
    esn_config = get_esn_mapping_config()

    return render_template('mapping_container.html',
                          operators=current_app.config['OPERATORS'],
                          current_operator=operator,
                          current_operator_title=op_config.get('title', operator),
                          domain_targets=domain_targets,
                          variable_targets=variable_targets,
                          spart_targets=spart_targets,
                          sharing_groups=sharing_groups,
                          sharing_cities=sharing_cities,
                          mappings=mappings,
                          targets_file=targets_file,
                          message=message,
                          esn_config=esn_config)
    
# ========== EXCEL MAPPING SETTINGS (ESN) ==========

from modules.config_store import get_esn_mapping_config, set_esn_mapping_config

@web_bp.route('/api/esn_mapping_config', methods=['GET'])
def api_get_esn_mapping_config():
    return jsonify(get_esn_mapping_config())


@web_bp.route('/api/esn_mapping_config', methods=['POST'])
def api_set_esn_mapping_config():
    data = request.get_json() or {}
    raw_columns = data.get('columns') or {}
    allowed = {'esn', 'lsn', 'operator', 'domain', 'ne_type', 'city', 'site'}

    clean = {}
    for k, v in raw_columns.items():
        if k not in allowed:
            continue
        v = (str(v) or '').strip().upper()
        if not v:
            continue
        if not all('A' <= ch <= 'Z' for ch in v):
            return jsonify({'error': f'Некорректная колонка для {k}: {v}'}), 400
        clean[k] = v

    if 'esn' not in clean:
        return jsonify({'error': 'Колонка ESN обязательна'}), 400

    set_esn_mapping_config(clean, data.get('has_header', True))
    return jsonify({'success': True, 'config': get_esn_mapping_config()})
    
@web_bp.route('/<operator>/base_targets', methods=['GET', 'POST'])
def base_targets(operator):
    # Редирект на excel_mapping
    return redirect(url_for('web.excel_mapping', operator=operator))

@web_bp.route('/api/license_details_status')
def api_license_details_status():
    from modules.capacity_mapper import load_ne_type_mapping
    import openpyxl
    mapping = load_ne_type_mapping()
    network_storage = current_app.config.get('network_storage_path', '')
    
    items = []
    for ne_type, info in mapping.items():
        file_path = os.path.join(network_storage, 'license_details', info.get('details_file', ''))
        exists = os.path.exists(file_path)
        count = 0
        if exists:
            try:
                wb = openpyxl.load_workbook(file_path, data_only=True)
                sheet_name = info.get('sheet_name')
                sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
                count = sheet.max_row - 1
            except:
                pass
        items.append({
            'ne_type': ne_type,
            'file': info.get('details_file', ''),
            'exists': exists,
            'count': count
        })
    
    return jsonify({'success': True, 'items': items})

# ========== STORAGE / NAMING CONFIG ==========

import modules.config_store as _cfg_store

DEFAULT_STRUCTURE = ['operator', 'ne_type', 'city', 'site', 'year']
ALLOWED_FOLDERS = {'operator', 'domain', 'ne_type', 'city', 'site', 'year',
                   'version', 'lsn', 'esn'}


def _normalize_structure_config(cfg):
    """Возвращает {domain: [levels]} с гарантированным 'default'."""
    fs = cfg.get('folder_structure')
    if isinstance(fs, list):
        # старая схема (глобальный список) → оборачиваем в default
        return {'default': fs or DEFAULT_STRUCTURE}
    if isinstance(fs, dict):
        out = {k: [f for f in v if f in ALLOWED_FOLDERS] for k, v in fs.items() if isinstance(v, list)}
        out.setdefault('default', DEFAULT_STRUCTURE)
        return out
    return {'default': DEFAULT_STRUCTURE}


@web_bp.route('/api/storage_config', methods=['GET'])
def api_get_storage_config():
    cfg = _cfg_store.load_config()
    structures = _normalize_structure_config(cfg)
    return jsonify({
        'folder_structure': structures,
        'domains': sorted(structures.keys()),
        'license_name_template': cfg.get('license_name_template',
            'LIC{ne_type}_{version}_{city}_{site}_{year}'),
        'available_folders': sorted(ALLOWED_FOLDERS),
        'available_placeholders': [
            'operator', 'domain', 'ne_type', 'city', 'site', 'year',
            'version', 'lsn', 'esn',
            'create_date', 'create_year', 'create_month', 'create_month_short', 'create_day',
        ],
    })


@web_bp.route('/api/storage_config', methods=['POST'])
def api_set_storage_config():
    data = request.get_json() or {}
    structures = data.get('folder_structure') or {}
    template = (data.get('license_name_template') or '').strip()

    # --- валидация структур ---
    if not isinstance(structures, dict) or 'default' not in structures:
        return jsonify({'error': 'Нужен хотя бы default-домен'}), 400
    clean = {}
    for domain, levels in structures.items():
        if not isinstance(levels, list) or not levels:
            return jsonify({'error': f'Пустая структура для домена {domain}'}), 400
        filtered = [f for f in levels if f in ALLOWED_FOLDERS]
        if len(filtered) != len(levels):
            return jsonify({'error': f'Недопустимый уровень для домена {domain}'}), 400
        clean[domain] = filtered

    # --- валидация шаблона ---
    if not template:
        return jsonify({'error': 'Шаблон имени не может быть пустым'}), 400
    if '.' in template:
        return jsonify({'error': 'Шаблон не должен содержать расширение (.dat/.xml) — оно добавляется автоматически'}), 400
    if '{ne_type}' not in template and '{lsn}' not in template:
        return jsonify({'error': 'Шаблон должен содержать {ne_type} или {lsn}'}), 400

    _cfg_store.save_config_section('folder_structure', clean)
    _cfg_store.save_config_section('license_name_template', template)
    return jsonify({
        'success': True,
        'folder_structure': clean,
        'license_name_template': template,
    })
    
    
# ========== REORGANIZE + BACKUP (для UI в настройках) ==========

from modules import bulk_reorganizer
import shutil as _shutil
import time as _time


@web_bp.route('/<operator>/reorganize/preview', methods=['POST'])
def reorganize_preview(operator):
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'error': 'Оператор не найден'}), 404

    remote_base = current_app.config.get('network_storage_path', '')
    if not remote_base:
        return jsonify({'error': 'Не указан network_storage_path'}), 400

    payload = request.get_json(silent=True) or {}
    operation = payload.get('operation', 'both')
    if operation not in ('rename', 'move', 'both'):
        return jsonify({'error': f'Неизвестная операция: {operation}'}), 400

    items = bulk_reorganizer.preview(operator, remote_base, operation=operation)
    stats = {
        'total': len(items),
        'ok': sum(1 for i in items if i['status'] == 'ok'),
        'skip': sum(1 for i in items if i['status'] == 'skip'),
        'conflict': sum(1 for i in items if i['status'] == 'conflict'),
        'error': sum(1 for i in items if i['status'] == 'error'),
    }
    return jsonify({
        'success': True, 'operation': operation,
        'stats': stats, 'items': items,
    })


@web_bp.route('/<operator>/reorganize/apply', methods=['POST'])
def reorganize_apply(operator):
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'error': 'Оператор не найден'}), 404

    remote_base = current_app.config.get('network_storage_path', '')
    if not remote_base:
        return jsonify({'error': 'Не указан network_storage_path'}), 400

    payload = request.get_json(silent=True) or {}
    operation = payload.get('operation', 'both')
    copy_mode = bool(payload.get('copy_mode', False))
    if operation not in ('rename', 'move', 'both'):
        return jsonify({'error': f'Неизвестная операция: {operation}'}), 400

    result = bulk_reorganizer.apply(
        operator, remote_base, operation=operation, copy_mode=copy_mode
    )
    return jsonify(result)

@web_bp.route('/<operator>/backup/operator_folder', methods=['POST'])
def backup_operator_folder(operator):
    """
    Копирует <remote_base>/<operator>/ в <remote_base>/_backup/<operator>_<timestamp>/
    Возвращает путь бэкапа и размер.
    """
    op_config = get_operator_config(operator)
    if not op_config:
        return jsonify({'error': 'Оператор не найден'}), 404

    remote_base = current_app.config.get('network_storage_path', '')
    if not remote_base:
        return jsonify({'error': 'Не указан network_storage_path'}), 400

    src = os.path.join(remote_base, operator)
    if not os.path.isdir(src):
        return jsonify({'success': False, 'error': f'Папка не найдена: {src}'}), 400

    timestamp = _time.strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(remote_base, '_backup', f'{operator}_{timestamp}')
    os.makedirs(backup_dir, exist_ok=True)

    try:
        # Считаем файлы для прогресса в логе
        copied = 0
        for root, _dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            dest_root = os.path.join(backup_dir, rel) if rel != '.' else backup_dir
            os.makedirs(dest_root, exist_ok=True)
            for f in files:
                _shutil.copy2(os.path.join(root, f), os.path.join(dest_root, f))
                copied += 1

        logger.info(f"Бэкап папки {operator}: {copied} файлов → {backup_dir}")
        return jsonify({
            'success': True,
            'backup_path': backup_dir,
            'files_copied': copied,
        })
    except Exception as e:
        logger.error(f"Ошибка бэкапа папки {operator}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    


