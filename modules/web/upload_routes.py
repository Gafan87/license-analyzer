from flask import Blueprint, render_template, request, jsonify
from modules.staging_service import StagingService

upload_bp = Blueprint('upload_bp', __name__)
staging_service = StagingService()


@upload_bp.route('/<operator>/upload')
def upload_page(operator):
    return render_template('upload_licenses.html', current_operator=operator)


@upload_bp.route('/api/staging/state', methods=['GET'])
def api_staging_state():
    operator = request.args.get('operator')
    return jsonify(staging_service.get_state(operator=operator))


@upload_bp.route('/api/staging/upload', methods=['POST'])
def api_staging_upload():
    operator = request.form.get('operator') or request.args.get('operator')
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'Файлы не переданы'}), 400
    result = staging_service.add_uploaded_files(files, operator=operator)
    return jsonify(result)


@upload_bp.route('/api/staging/scan_folder', methods=['POST'])
def api_staging_scan_folder():
    data = request.get_json(silent=True) or {}
    folder_path = (data.get('folder_path') or '').strip()
    operator = data.get('operator') or request.args.get('operator')
    try:
        result = staging_service.scan_local_folder(folder_path, operator=operator)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Ошибка сканирования: {e}'}), 500


@upload_bp.route('/api/staging/compare', methods=['GET'])
def api_staging_compare():
    operator = request.args.get('operator')
    try:
        data = staging_service.build_comparison(operator=operator)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Ошибка сравнения: {e}'}), 500


@upload_bp.route('/api/staging/toggle_select', methods=['POST'])
def api_staging_toggle_select():
    data = request.get_json(silent=True) or {}
    file_id = data.get('id')
    selected = data.get('selected', True)
    operator = data.get('operator')
    state = staging_service.toggle_select(file_id, selected, operator=operator)
    return jsonify(state)


@upload_bp.route('/api/staging/file/<file_id>', methods=['DELETE'])
def api_staging_delete_file(file_id):
    operator = request.args.get('operator')
    state = staging_service.remove_file(file_id, operator=operator)
    return jsonify(state)


@upload_bp.route('/api/staging/clear', methods=['DELETE'])
def api_staging_clear():
    state = staging_service.clear_session()
    return jsonify(state)

@upload_bp.route('/api/staging/preview_paths', methods=['GET'])
def api_staging_preview_paths():
    operator = request.args.get('operator')
    try:
        data = staging_service.preview_import_paths(operator=operator)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Ошибка расчёта путей: {e}'}), 500


@upload_bp.route('/api/staging/commit', methods=['POST'])
def api_staging_commit():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or request.args.get('operator')
    copy_files = data.get('copy_files', True)
    try:
        result = staging_service.commit_batch(operator=operator, copy_files=copy_files)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Ошибка импорта в БД: {e}'}), 500


@upload_bp.route('/api/staging/db_licenses', methods=['GET'])
def api_staging_db_licenses():
    operator = request.args.get('operator') or session.get('operator')
    only_web = request.args.get('only_web', '0').lower() in ('1', 'true', 'yes')
    return jsonify(staging_service.list_db_licenses(operator=operator, only_web_upload=only_web))


@upload_bp.route('/api/staging/load_from_db', methods=['POST'])
def api_staging_load_from_db():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or session.get('operator')
    license_ids = data.get('license_ids') or []
    clear_first = bool(data.get('clear_first', True))
    return jsonify(staging_service.load_from_db_licenses(license_ids, operator=operator, clear_first=clear_first))


@upload_bp.route('/api/staging/copy_to_new_folder', methods=['POST'])
def api_staging_copy_to_new_folder():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or session.get('operator')
    license_ids = data.get('license_ids') or []
    return jsonify(staging_service.copy_db_licenses_to_new_folder(license_ids, operator=operator))


@upload_bp.route('/api/staging/sessions', methods=['GET'])
def api_staging_sessions():
    operator = request.args.get('operator') or session.get('operator')
    return jsonify(staging_service.list_upload_sessions(operator=operator))


@upload_bp.route('/api/staging/package_preview', methods=['POST'])
def api_staging_package_preview():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or session.get('operator')
    return jsonify(staging_service.preview_package_export(
        data.get('session_ids') or [],
        operator=operator,
        mode=data.get('mode', 'structure'),
        folder_comment=data.get('folder_comment', '')
    ))


@upload_bp.route('/api/staging/package_export', methods=['POST'])
def api_staging_package_export():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or session.get('operator')
    return jsonify(staging_service.export_package(
        data.get('session_ids') or [],
        operator=operator,
        mode=data.get('mode', 'structure'),
        folder_comment=data.get('folder_comment', ''),
        include_html=bool(data.get('include_html', True)),
        include_zip=bool(data.get('include_zip', True)),
        include_xlsx=bool(data.get('include_xlsx', False)),
        html_content=data.get('html_content')
    ))


@upload_bp.route('/api/staging/scan_temporary', methods=['POST'])
def api_staging_scan_temporary():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or request.args.get('operator') or session.get('operator')
    try:
        result = staging_service.scan_temporary_folder(operator=operator)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Ошибка сканирования _temporary: {e}'}), 500


@upload_bp.route('/api/staging/rename_in_source', methods=['POST'])
def api_staging_rename_in_source():
    data = request.get_json(silent=True) or {}
    operator = data.get('operator') or request.args.get('operator') or session.get('operator')
    try:
        result = staging_service.rename_in_source_folder(operator=operator)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Ошибка переименования: {e}'}), 500
