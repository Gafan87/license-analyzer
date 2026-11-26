import os
import re
import json
import uuid
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename

from modules.parser_dat import parse_dat_license
from modules.parser_xml import parse_xml_license
from modules.esn_mapper import get_mapping_by_esn
from modules.database import (
    get_all_licenses_for_esn,
    get_license_by_id,
    get_base_targets,
    get_connection,
)

ALLOWED_EXTENSIONS = {'.dat', '.xml'}
STAGING_ROOT = os.path.join('data', 'staging', 'current')
PARSED_DIR = os.path.join(STAGING_ROOT, 'parsed')
STATE_FILE = os.path.join(STAGING_ROOT, 'state.json')


def _to_number(val):
    if val is None or val == '':
        return 0
    try:
        f = float(val)
        return int(f) if f.is_integer() else round(f, 2)
    except Exception:
        return 0


def _extract_resources_map(parsed_obj):
    res_map = {}
    if not isinstance(parsed_obj, dict):
        return res_map

    resources = parsed_obj.get('resources')
    if not resources and parsed_obj.get('parsed_cache'):
        pc = parsed_obj.get('parsed_cache')
        if isinstance(pc, str):
            try:
                pc = json.loads(pc)
            except Exception:
                pc = {}
        if isinstance(pc, dict):
            resources = pc.get('resources')

    if isinstance(resources, list):
        for item in resources:
            if not isinstance(item, dict):
                continue
            name = item.get('name') or item.get('key') or item.get('capacity_key')
            if not name:
                continue
            total_val = item.get('total_value')
            if total_val is None:
                total_val = item.get('value', 0)
            total_num = _to_number(total_val)
            perm_num = _to_number(item.get('permanent_value', 0))
            if 'dated_value' in item and item.get('dated_value') is not None:
                dated_num = _to_number(item.get('dated_value', 0))
            else:
                dated_num = max(0, total_num - perm_num)
                if isinstance(dated_num, float) and dated_num.is_integer():
                    dated_num = int(dated_num)
            vdate = item.get('valid_date') or item.get('latest_date') or item.get('dated_date') or ''
            if not vdate and perm_num > 0 and dated_num == 0:
                vdate = 'PERMANENT'
            res_map[str(name)] = {
                'total': total_num,
                'permanent': perm_num,
                'dated': dated_num,
                'valid_date': str(vdate),
            }
    elif isinstance(resources, dict):
        for k, v in resources.items():
            if isinstance(v, dict):
                total_num = _to_number(v.get('total', v.get('total_value', v.get('value', 0))))
                perm_num = _to_number(v.get('permanent', v.get('permanent_value', 0)))
                dated_num = _to_number(v.get('dated', v.get('dated_value', max(0, total_num - perm_num))))
                res_map[str(k)] = {
                    'total': total_num,
                    'permanent': perm_num,
                    'dated': dated_num,
                    'valid_date': str(v.get('valid_date', '')),
                }
            else:
                num = _to_number(v)
                res_map[str(k)] = {'total': num, 'permanent': 0, 'dated': num, 'valid_date': ''}
    return res_map


def _extract_targets_map(raw_targets):
    t_map = {}
    if not raw_targets:
        return t_map
    if isinstance(raw_targets, dict):
        for k, v in raw_targets.items():
            t_map[str(k)] = _to_number(v)
    elif isinstance(raw_targets, list):
        for row in raw_targets:
            if isinstance(row, dict):
                key = row.get('capacity_key') or row.get('key') or row.get('name')
                val = row.get('target_value') if 'target_value' in row else row.get('value')
                if key:
                    t_map[str(key)] = _to_number(val)
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                t_map[str(row[0])] = _to_number(row[1])
    return t_map


class StagingService:
    def __init__(self):
        os.makedirs(STAGING_ROOT, exist_ok=True)
        os.makedirs(PARSED_DIR, exist_ok=True)

    def _load_state(self):
        if not os.path.exists(STATE_FILE):
            return {'files': [], 'updated_at': None}
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {'files': [], 'updated_at': None}

    def _save_state(self, state):
        os.makedirs(STAGING_ROOT, exist_ok=True)
        os.makedirs(PARSED_DIR, exist_ok=True)
        state['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _parsed_cache_path(self, file_id):
        return os.path.join(PARSED_DIR, f'{file_id}.json')

    def _is_allowed(self, filename):
        _, ext = os.path.splitext(filename.lower())
        return ext in ALLOWED_EXTENSIONS

    def _parse_and_enrich_entry(self, entry, operator=None):
        fpath = entry.get('saved_path')
        ext = entry.get('ext', '').lower()
        if not fpath or not os.path.exists(fpath):
            entry['status'] = 'error'
            entry['status_text'] = 'Файл не найден на диске'
            entry['selected'] = False
            return entry

        try:
            parsed = parse_dat_license(fpath) if ext == '.dat' else parse_xml_license(fpath)
            if not isinstance(parsed, dict):
                raise ValueError('Парсер вернул пустой результат')

            esn = (parsed.get('esn') or '').strip()
            lsn = (parsed.get('lsn') or '').strip()
            entry['esn'] = esn or None
            entry['lsn'] = lsn or None
            entry['product'] = parsed.get('product') or ''
            entry['version'] = parsed.get('version') or ''
            entry['node'] = parsed.get('node') or ''
            entry['valid_date'] = parsed.get('valid_date') or ''
            entry['create_time'] = parsed.get('create_time') or ''
            entry['parsed'] = True
            entry['cache_v'] = 2

            res_map = _extract_resources_map(parsed)
            spart_hierarchy = parsed.get('spart_hierarchy') or {'sparts': [], 'orphan_bparts': []}
            os.makedirs(PARSED_DIR, exist_ok=True)
            with open(self._parsed_cache_path(entry['id']), 'w', encoding='utf-8') as pf:
                json.dump({
                    'resources': res_map,
                    'spart_hierarchy': spart_hierarchy,
                }, pf, ensure_ascii=False)
            entry['resources_count'] = len(res_map)

            mapping = get_mapping_by_esn(esn) if esn else None
            if isinstance(mapping, dict):
                entry['domain'] = mapping.get('domain') or 'unknown'
                entry['sub_domain'] = mapping.get('sub_domain') or ''
                entry['city'] = mapping.get('city') or ''
                entry['city_full'] = mapping.get('city_full') or mapping.get('city') or ''
                entry['ne_type'] = mapping.get('ne_type') or ''
                entry['site'] = mapping.get('site') or ''
                entry['mapped_operator'] = mapping.get('operator') or ''
            else:
                entry['domain'] = 'unknown'
                entry['sub_domain'] = ''
                entry['city'] = ''
                entry['city_full'] = ''
                entry['ne_type'] = ''
                entry['site'] = ''
                entry['mapped_operator'] = ''

            target_op = operator or entry.get('mapped_operator') or ''
            db_lics = get_all_licenses_for_esn(target_op, esn) if (target_op and esn) else []
            is_dup = any((lic.get('lsn') or '').strip() == lsn for lic in db_lics if lsn)

            if not esn:
                entry['status'] = 'error'
                entry['status_text'] = 'Не удалось извлечь ESN'
                entry['selected'] = False
            elif is_dup:
                entry['status'] = 'duplicate'
                entry['status_text'] = 'Дубликат (LSN уже в БД)'
                entry['selected'] = False
            elif not mapping:
                entry['status'] = 'unknown_esn'
                entry['status_text'] = 'ESN не найден в маппинге'
                entry['selected'] = True
            elif operator and entry['mapped_operator'] and entry['mapped_operator'].lower() != operator.lower():
                entry['status'] = 'ready'
                entry['status_text'] = f"Внимание: в маппинге оператор {entry['mapped_operator']}"
                entry['selected'] = True
            else:
                entry['status'] = 'ready'
                entry['status_text'] = 'Готов к сравнению'
                entry['selected'] = True

        except Exception as e:
            entry['status'] = 'error'
            entry['status_text'] = f'Ошибка парсинга: {str(e)[:80]}'
            entry['selected'] = False
            entry['parsed'] = True

        return entry

    def _build_file_entry(self, original_name, saved_path, operator=None):
        _, ext = os.path.splitext(original_name.lower())
        entry = {
            'id': uuid.uuid4().hex[:10],
            'original_name': original_name,
            'ext': ext,
            'saved_path': saved_path,
            'size_kb': round(os.path.getsize(saved_path) / 1024, 1),
            'esn': None,
            'lsn': None,
            'domain': 'unknown',
            'sub_domain': '',
            'city': '',
            'city_full': '',
            'ne_type': '',
            'site': '',
            'mapped_operator': '',
            'status': 'ready',
            'status_text': 'Ожидает сравнения',
            'selected': True,
            'parsed': False,
            'cache_v': 2,
        }
        return self._parse_and_enrich_entry(entry, operator=operator)

    def get_state(self, operator=None):
        state = self._load_state()
        files = state.get('files', [])
        changed = False
        for f in files:
            if not f.get('parsed') or f.get('cache_v') != 2 or not os.path.exists(self._parsed_cache_path(f['id'])):
                self._parse_and_enrich_entry(f, operator=operator)
                changed = True
        if changed:
            self._save_state(state)

        stats = {
            'total': len(files),
            'ready': sum(1 for f in files if f['status'] == 'ready'),
            'duplicate': sum(1 for f in files if f['status'] == 'duplicate'),
            'unknown_esn': sum(1 for f in files if f['status'] == 'unknown_esn'),
            'errors': sum(1 for f in files if f['status'] == 'error'),
            'selected': sum(1 for f in files if f.get('selected')),
        }
        return {'files': files, 'stats': stats, 'updated_at': state.get('updated_at')}

    def add_uploaded_files(self, file_storages, operator=None):
        state = self._load_state()
        added = 0
        skipped = 0

        for fs in file_storages:
            if not fs or not fs.filename:
                continue
            base_name = os.path.basename(fs.filename)
            if not self._is_allowed(base_name):
                skipped += 1
                continue

            safe_name = f"{uuid.uuid4().hex[:6]}_{secure_filename(base_name)}"
            target_path = os.path.join(STAGING_ROOT, safe_name)
            fs.save(target_path)

            state['files'].append(self._build_file_entry(base_name, target_path, operator=operator))
            added += 1

        self._save_state(state)
        return {'added': added, 'skipped': skipped, 'state': self.get_state(operator=operator)}

    def scan_local_folder(self, folder_path, operator=None):
        if not folder_path or not os.path.isdir(folder_path):
            raise ValueError(f"Папка не найдена: {folder_path}")

        state = self._load_state()
        added = 0
        skipped = 0

        for root, _, filenames in os.walk(folder_path):
            for fname in filenames:
                if not self._is_allowed(fname):
                    skipped += 1
                    continue
                src_path = os.path.join(root, fname)
                safe_name = f"{uuid.uuid4().hex[:6]}_{secure_filename(fname)}"
                target_path = os.path.join(STAGING_ROOT, safe_name)
                shutil.copy2(src_path, target_path)

                entry = self._build_file_entry(fname, target_path, operator=operator)
                entry['source_path'] = src_path
                state['files'].append(entry)
                added += 1

        self._save_state(state)
        return {'added': added, 'skipped': skipped, 'state': self.get_state(operator=operator)}

    def scan_temporary_folder(self, operator=None):
        base_dir = self._get_operator_storage_base(operator)
        temp_dir = os.path.join(os.path.normpath(base_dir), '_temporary')
        return self.scan_local_folder(temp_dir, operator=operator)

    def rename_in_source_folder(self, operator=None):
        prev = self.preview_import_paths(operator=operator)
        name_by_id = {}
        name_by_orig = {}
        for it in prev.get('items', []):
            if it.get('id'):
                name_by_id[it['id']] = it.get('new_name')
            if it.get('original_name'):
                name_by_orig[it['original_name']] = it.get('new_name')

        state = self._load_state()
        renamed = 0
        skipped = 0
        errors = []

        for f in state.get('files', []):
            if not f.get('selected'):
                continue
            orig_name = f.get('original_name') or ''
            src_path = f.get('source_path') or ''
            if not src_path or not os.path.isfile(src_path):
                skipped += 1
                errors.append(f"{orig_name}: нет исходного пути на диске (загружен через браузер или файл перемещён)")
                continue

            new_name = name_by_id.get(f.get('id')) or name_by_orig.get(orig_name)
            if not new_name:
                skipped += 1
                errors.append(f"{orig_name}: не удалось рассчитать новое имя")
                continue

            cur_name = os.path.basename(src_path)
            if cur_name == new_name:
                skipped += 1
                continue

            dst_path = os.path.join(os.path.dirname(src_path), new_name)
            if os.path.exists(dst_path) and os.path.normcase(dst_path) != os.path.normcase(src_path):
                errors.append(f"{orig_name}: целевой файл уже существует ({new_name})")
                continue

            try:
                os.rename(src_path, dst_path)
                f['source_path'] = dst_path
                f['original_name'] = new_name
                renamed += 1
            except Exception as e:
                errors.append(f"{orig_name}: {e}")

        self._save_state(state)
        return {
            'renamed': renamed,
            'skipped': skipped,
            'errors': errors,
            'state': self.get_state(operator=operator),
        }

    def toggle_select(self, file_id, selected, operator=None):
        state = self._load_state()
        for f in state.get('files', []):
            if f['id'] == file_id:
                f['selected'] = bool(selected)
                break
        self._save_state(state)
        return self.get_state(operator=operator)

    def remove_file(self, file_id, operator=None):
        state = self._load_state()
        new_files = []
        for f in state.get('files', []):
            if f['id'] == file_id:
                if os.path.exists(f['saved_path']):
                    os.remove(f['saved_path'])
                p_path = self._parsed_cache_path(file_id)
                if os.path.exists(p_path):
                    os.remove(p_path)
            else:
                new_files.append(f)
        state['files'] = new_files
        self._save_state(state)
        return self.get_state(operator=operator)

    def clear_session(self):
        if os.path.exists(STAGING_ROOT):
            shutil.rmtree(STAGING_ROOT, ignore_errors=True)
        os.makedirs(STAGING_ROOT, exist_ok=True)
        os.makedirs(PARSED_DIR, exist_ok=True)
        return self.get_state()

    def _get_network_storage_path(self):
        try:
            from flask import current_app
            p = current_app.config.get('network_storage_path')
            if p:
                return p
        except Exception:
            pass
        from modules.config_store import load_config
        cfg = load_config(force_reload=False) or {}
        return cfg.get('network_storage_path') or ''

    def _load_full_list_for_ne(self, domain, ne_type, operator):
        from modules.capacity_mapper import load_full_capacity_list, resolve_ne_type
        if not domain:
            return []
        net_path = self._get_network_storage_path()
        op_lower = (operator or '').strip().lower() or None
        resolved_ne = resolve_ne_type(ne_type) if ne_type else None
        try:
            return load_full_capacity_list(domain, net_path, ne_type=resolved_ne, operator_name=op_lower) or []
        except Exception:
            return []

    def _evaluate_bpart_target(self, formula_str, parent_spart_target, targets_map):
        from modules.capacity_mapper import roundup
        if not formula_str:
            return None
        formula = str(formula_str).strip()
        if not formula:
            return None

        if formula.lower().startswith('fix:'):
            if parent_spart_target is None or parent_spart_target == '' or parent_spart_target == 0:
                return None
            try:
                return _to_number(roundup(float(formula[4:]), 0))
            except (ValueError, TypeError):
                return None

        if formula.endswith('%'):
            try:
                pct = float(formula[:-1]) / 100
                if parent_spart_target is not None:
                    return _to_number(roundup(parent_spart_target * pct, 0))
                return None
            except (ValueError, TypeError):
                return None

        try:
            num = float(formula)
            if parent_spart_target is not None:
                return _to_number(roundup(parent_spart_target * num, 0))
            return None
        except ValueError:
            pass

        if formula in targets_map:
            return targets_map[formula]

        formula_lower = formula.lower()
        for k, v in targets_map.items():
            if k.lower() == formula_lower:
                return v

        if '+' in formula:
            parts = [p.strip() for p in formula.split('+')]
            total = 0
            all_found = True
            for part in parts:
                if part in targets_map:
                    total += targets_map[part]
                else:
                    found = False
                    for k, v in targets_map.items():
                        if k.lower() == part.lower():
                            total += v
                            found = True
                            break
                    if not found:
                        all_found = False
                        break
            if all_found:
                return _to_number(roundup(total, 0))

        return None

    def _load_license_targets(self, operator, ne_type, city, full_list=None):
        t_map = {}
        if not (operator and ne_type and city):
            return t_map
        from modules.capacity_mapper import resolve_ne_type
        raw_ne = ne_type.strip()
        resolved_ne = resolve_ne_type(raw_ne)
        candidates = [resolved_ne] if resolved_ne else []
        if raw_ne and raw_ne not in candidates:
            candidates.append(raw_ne)

        all_lt = {}
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            for cand in candidates:
                rows = cur.execute(
                    """
                    SELECT capacity_key, target_value, item_type
                    FROM license_targets
                    WHERE LOWER(operator) = LOWER(?)
                      AND LOWER(city) = LOWER(?)
                      AND ne_type = ?
                    """,
                    (operator, city, cand),
                ).fetchall()
                if rows:
                    for key, val, item_type in rows:
                        if not key:
                            continue
                        k_str = str(key).strip()
                        num = _to_number(val)
                        all_lt[k_str] = num
                        it_low = (item_type or '').strip().lower()
                        if it_low not in ('variable', 'target'):
                            t_map[k_str] = num
                    break
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        # Обогащаем targets_map SPart-ссылками (1-в-1 как в get_xml_hierarchy / get_dat_hierarchy)
        ref_pattern_ops = ['*', '/', '+', '-', '(', ')', '%']
        if full_list and all_lt:
            for item in full_list:
                if item.get('type') != 'spart':
                    continue
                sp_name = item.get('name')
                if not sp_name or sp_name in t_map:
                    continue
                formula = item.get('formula')
                if not formula:
                    continue
                f_str = str(formula).strip()
                if f_str in all_lt and not any(op in f_str for op in ref_pattern_ops):
                    t_map[sp_name] = all_lt[f_str]
                    all_lt[sp_name] = all_lt[f_str]

        # Вычисляем цели BPart с привязкой к конкретному родительскому SPart
        bpart_targets = {}
        if full_list and (all_lt or t_map):
            for item in full_list:
                if item.get('type') != 'bpart':
                    continue
                bp_name = item.get('name')
                if not bp_name:
                    continue
                formula = item.get('formula')
                parent = item.get('parent')
                parent_tgt = t_map.get(parent) if parent else None
                if formula:
                    bp_tgt = self._evaluate_bpart_target(formula, parent_tgt, all_lt)
                    if bp_tgt is not None:
                        if parent:
                            bpart_targets[(parent, bp_name)] = bp_tgt
                        elif bp_name not in t_map:
                            t_map[bp_name] = bp_tgt

        return t_map, bpart_targets

    def _compute_planned_name(self, entry, operator):
        """Вычисляет планируемое новое имя файла (как в preview_import_paths)."""
        try:
            from modules.bulk_reorganizer import _target_path
            remote_base = self._get_operator_storage_base(operator)
            lic_dict = self._build_lic_dict_for_reorg(entry, operator)
            target_full = _target_path(remote_base, lic_dict, 'both')
            return os.path.basename(target_full)
        except Exception:
            return entry.get('original_name') or ''

    def _get_ne_sharing_info(self, operator, ne_type, city):
        """Возвращает (share_group, sharing_coeff) для NE и города из targets.xlsx (с кэшем на 60 сек)."""
        import time
        from modules.config_store import load_config
        from modules.capacity_mapper import load_sharing_from_excel, resolve_ne_type

        if not hasattr(self, '_sharing_excel_cache'):
            self._sharing_excel_cache = {'ts': 0, 'data': None}

        now = time.time()
        sharing_data = self._sharing_excel_cache.get('data')
        if not sharing_data or (now - self._sharing_excel_cache.get('ts', 0) > 60):
            sharing_data = {}
            try:
                cfg = load_config(force_reload=True) or {}
                m_path = cfg.get('mapping_path') or ''
                if m_path and os.path.isdir(m_path):
                    xlsx_files = [
                        fn for fn in os.listdir(m_path)
                        if fn.lower().endswith('.xlsx') and not fn.startswith('~$')
                    ]
                    xlsx_files.sort(key=lambda fn: (0 if 'target' in fn.lower() else (1 if 'sharing' in fn.lower() else 2), fn.lower()))
                    for fn in xlsx_files:
                        res = load_sharing_from_excel(os.path.join(m_path, fn)) or {}
                        if res:
                            sharing_data = res
                            break
            except Exception:
                sharing_data = {}
            self._sharing_excel_cache = {'ts': now, 'data': sharing_data}

        op_low = (operator or '').strip().lower()
        op_map = {}
        for k, v in (sharing_data or {}).items():
            if isinstance(k, tuple) and len(k) == 2:
                if str(k[0]).strip().lower() == op_low:
                    op_map[str(k[1]).strip()] = v
            elif str(k).strip().lower() == op_low and isinstance(v, dict):
                op_map = v

        raw_ne = (ne_type or '').strip()
        resolved_ne = resolve_ne_type(raw_ne)
        cands = [resolved_ne] if resolved_ne else []
        if raw_ne and raw_ne not in cands:
            cands.append(raw_ne)

        ne_info = None
        for c in cands:
            if c in op_map:
                ne_info = op_map[c]
                break
            for k, v in op_map.items():
                if str(k).strip().lower() == str(c).strip().lower():
                    ne_info = v
                    break
            if ne_info:
                break

        if not isinstance(ne_info, dict):
            return '', 1

        sg = (ne_info.get('share_group') or '').strip()
        if not sg and ne_info.get('copy_from'):
            src_info = op_map.get(ne_info['copy_from']) or {}
            sg = (src_info.get('share_group') or '').strip()

        sh_coeff = 1
        cities_map = ne_info.get('cities') or {}
        city_low = (city or '').strip().lower()
        for ck, cv in cities_map.items():
            if str(ck).strip().lower() == city_low:
                val = _to_number(cv)
                if val and val > 0:
                    sh_coeff = val
                break

        return sg, sh_coeff
    def _load_city_targets_summary(self, operator, ne_type, city):
        """Возвращает сводку Targets на город и на 1 NE (с коэффициентом шаринга) из SQLite."""
        if not (operator and ne_type and city):
            return {'rows': [], 'has_sharing': False, 'sharing_coeff': None}

        from modules.capacity_mapper import resolve_ne_type
        raw_ne = ne_type.strip()
        resolved_ne = resolve_ne_type(raw_ne)
        candidates = [resolved_ne] if resolved_ne else []
        if raw_ne and raw_ne not in candidates:
            candidates.append(raw_ne)

        share_group, sh_from_excel = self._get_ne_sharing_info(operator, raw_ne, city)
        sg_low = (share_group or '').strip().lower()

        rows_out = []
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            # Обычная логика (с фильтрацией по group_name для PS,vEPC: GGSN / SGSN)
            if not rows_out:
                for cand in candidates:
                    db_rows = cur.execute(
                        """
                        SELECT lt.capacity_key, lt.target_value, dt.value, dt.unit, dt.domain, dt.group_name
                        FROM license_targets lt
                        LEFT JOIN domain_targets dt
                          ON LOWER(dt.operator) = LOWER(lt.operator)
                         AND LOWER(dt.city) = LOWER(lt.city)
                         AND dt.target_key = lt.capacity_key
                        WHERE LOWER(lt.operator) = LOWER(?)
                          AND LOWER(lt.city) = LOWER(?)
                          AND lt.ne_type = ?
                          AND LOWER(lt.item_type) = 'target'
                        ORDER BY COALESCE(dt.sort_order, 9999), lt.capacity_key
                        """,
                        (operator, city, cand),
                    ).fetchall()
                    if db_rows:
                        filtered_rows = db_rows
                        if sg_low in ('ggsn', 'sgsn', 'charge'):
                            grp_only = [
                                r for r in db_rows
                                if not r[5] or str(r[5]).strip().lower() == sg_low
                            ]
                            if grp_only:
                                filtered_rows = grp_only
                        sh = sh_from_excel if (sh_from_excel and sh_from_excel > 0) else 1
                        if float(sh).is_integer():
                            sh = int(sh)
                        sh = sh_from_excel if (sh_from_excel and sh_from_excel > 0) else 1
                        if float(sh).is_integer():
                            sh = int(sh)
                        for key, ne_val, city_val, unit, _, _ in filtered_rows:
                            ne_num = _to_number(ne_val)
                            city_num = _to_number(city_val) if city_val is not None else None
                            rows_out.append({
                                'key': str(key).strip(),
                                'unit': (unit or '').strip(),
                                'city_val': city_num,
                                'ne_val': ne_num,
                                'sharing': sh,
                            })
                        var_rows = cur.execute(
                            """
                            SELECT capacity_key, target_value
                            FROM license_targets
                            WHERE LOWER(operator) = LOWER(?)
                              AND LOWER(city) = LOWER(?)
                              AND ne_type = ?
                              AND LOWER(item_type) = 'variable'
                              AND LOWER(capacity_key) IN ('total_sau', 'total_session')
                            ORDER BY capacity_key
                            """,
                            (operator, city, cand),
                        ).fetchall()
                        for vkey, vval in var_rows:
                            ne_num = _to_number(vval)
                            city_num = round(ne_num * sh, 2) if (ne_num is not None and sh > 0) else ne_num
                            if city_num is not None and float(city_num).is_integer():
                                city_num = int(city_num)
                            rows_out.append({
                                'key': str(vkey).strip(),
                                'unit': '',
                                'city_val': city_num,
                                'ne_val': ne_num,
                                'sharing': sh,
                            })
                        break

                # Фоллбэк напрямую из domain_targets для PS,vEPC (GGSN / SGSN), если в license_targets нет строк
                if not rows_out and sg_low in ('ggsn', 'sgsn'):
                    dt_rows = cur.execute(
                        """
                        SELECT target_key, unit, value
                        FROM domain_targets
                        WHERE LOWER(operator) = LOWER(?)
                          AND LOWER(city) = LOWER(?)
                          AND LOWER(domain) = 'ps,vepc'
                          AND LOWER(group_name) = LOWER(?)
                        ORDER BY COALESCE(sort_order, 9999), target_key
                        """,
                        (operator, city, share_group),
                    ).fetchall()
                    sh = sh_from_excel if (sh_from_excel and sh_from_excel > 0) else 1
                    for tkey, unit, val in dt_rows:
                        city_num = _to_number(val)
                        ne_raw = round(city_num / sh, 2) if sh > 0 else city_num
                        ne_num = int(ne_raw) if float(ne_raw).is_integer() else ne_raw
                        rows_out.append({
                            'key': str(tkey or '').strip(),
                            'unit': (unit or '').strip(),
                            'city_val': city_num,
                            'ne_val': ne_num,
                            'sharing': sh,
                        })
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        sh_vals = [r['sharing'] for r in rows_out if r['sharing'] and r['sharing'] != 1]
        has_sharing = len(sh_vals) > 0
        sharing_coeff = sh_vals[0] if has_sharing else 1
        return {
            'rows': rows_out,
            'has_sharing': has_sharing,
            'sharing_coeff': sharing_coeff,
        }
    def _make_row(self, key, new_info, db_info, tgt_val, row_type='item', description='', dimension='', part_number=''):
        new_total = new_info.get('total') if new_info else None
        new_perm = new_info.get('permanent') if new_info else None
        new_dated = new_info.get('dated') if new_info else None
        vdate = (new_info or {}).get('valid_date', '')

        db_total = db_info.get('total') if db_info else None
        db_perm = db_info.get('permanent') if db_info else None
        db_dated = db_info.get('dated') if db_info else None
        db_vdate = (db_info or {}).get('valid_date', '')

        delta_total = round((new_total or 0) - (db_total or 0), 2)
        if isinstance(delta_total, float) and delta_total.is_integer():
            delta_total = int(delta_total)

        status = 'none'
        if tgt_val is not None:
            status = 'shortage' if (new_total or 0) < tgt_val else 'ok'

        return {
            'key': key,
            'row_type': row_type,
            'new_total': new_total,
            'new_perm': new_perm,
            'new_dated': new_dated,
            'db_total': db_total,
            'db_perm': db_perm,
            'db_dated': db_dated,
            'delta_total': delta_total,
            'target_val': tgt_val,
            'valid_date': vdate,
            'db_valid_date': db_vdate,
            'status': status,
            'description': description or '',
            'dimension': dimension or '',
            'part_number': part_number or '',
        }

    def build_comparison(self, operator=None):
        try:
            from modules.capacity_mapper import clear_cache
            clear_cache()
        except Exception:
            pass
        state_data = self.get_state(operator=operator)
        files = state_data.get('files', [])
        items = []

        for f in files:
            fid = f['id']
            new_res = {}
            spart_hierarchy = {'sparts': [], 'orphan_bparts': []}
            p_path = self._parsed_cache_path(fid)
            if os.path.exists(p_path):
                try:
                    with open(p_path, 'r', encoding='utf-8') as pf:
                        cached = json.load(pf)
                        new_res = cached.get('resources', {})
                        spart_hierarchy = cached.get('spart_hierarchy') or {'sparts': [], 'orphan_bparts': []}
                except Exception:
                    pass

            esn = f.get('esn')
            target_op = operator or f.get('mapped_operator') or ''

            db_lic_meta = None
            db_res = {}
            if target_op and esn:
                db_lics = get_all_licenses_for_esn(target_op, esn) or []
                if db_lics:
                    db_lics_sorted = sorted(
                        db_lics,
                        key=lambda x: (x.get('create_time') or '', x.get('id') or 0),
                        reverse=True
                    )
                    latest = db_lics_sorted[0]
                    db_lic_meta = {
                        'id': latest.get('id'),
                        'filename': latest.get('filename') or '',
                        'lsn': latest.get('lsn') or '',
                        'valid_date': latest.get('valid_date') or '',
                        'create_time': latest.get('create_time') or '',
                        'version': latest.get('version') or '',
                    }
                    full_db = get_license_by_id(latest.get('id')) if latest.get('id') else latest
                    db_res = _extract_resources_map(full_db or latest)

            full_list = self._load_full_list_for_ne(
                f.get('domain'),
                f.get('ne_type'),
                target_op
            )
            descriptions = {}
            bpart_meta = {}
            spart_order = {}
            section_map = {}
            cur_section = ''
            for it in full_list:
                nm = it.get('name')
                if not nm:
                    continue
                if it.get('type') == 'section':
                    cur_section = nm
                    continue
                if nm not in descriptions:
                    descriptions[nm] = it
                if cur_section and nm not in section_map:
                    section_map[nm] = cur_section
                if it.get('type') == 'bpart' and it.get('parent'):
                    bpart_meta[(it['parent'], nm)] = it
                elif nm not in spart_order:
                    spart_order[nm] = it.get('sort_order', 9999)

            targets_map = {}
            bpart_targets = {}
            if target_op and f.get('ne_type') and f.get('city'):
                lt_map, bpart_targets = self._load_license_targets(
                    target_op, f.get('ne_type'), f.get('city'), full_list=full_list
                )
                targets_map.update(lt_map)
                try:
                    raw_targets = get_base_targets(
                        target_op,
                        f.get('ne_type'),
                        f.get('city'),
                        f.get('site') or ''
                    )
                    targets_map.update(_extract_targets_map(raw_targets))
                except Exception:
                    pass

            # Строим иерархию Spart -> Bpart
            spart_groups = []
            used_keys = set()
            sparts_raw = spart_hierarchy.get('sparts') or []

            if sparts_raw:
                # Сценарий XML: SPart есть в самой лицензии
                for sp in sparts_raw:
                    sp_name = str(sp.get('name') or '')
                    if not sp_name:
                        continue
                    used_keys.add(sp_name)
                    sp_new = {
                        'total': _to_number(sp.get('value', 0)),
                        'permanent': _to_number(sp.get('permanent_value', 0)),
                        'dated': _to_number(sp.get('dated_value', 0)),
                        'valid_date': str(sp.get('valid_date') or sp.get('dated_date') or ''),
                    }
                    sp_row = self._make_row(
                        sp_name, sp_new, db_res.get(sp_name), targets_map.get(sp_name), 'spart',
                        (descriptions.get(sp_name) or {}).get('description', ''), (descriptions.get(sp_name) or {}).get('dimension', ''), (descriptions.get(sp_name) or {}).get('part_number', '')
                    )

                    bpart_rows = []
                    for bp in sp.get('bparts') or []:
                        bp_name = str(bp.get('name') or '')
                        if not bp_name:
                            continue
                        used_keys.add(bp_name)
                        bp_new = {
                            'total': _to_number(bp.get('value', 0)),
                            'permanent': _to_number(bp.get('permanent_value', 0)),
                            'dated': _to_number(bp.get('dated_value', 0)),
                            'valid_date': str(bp.get('valid_date') or bp.get('dated_date') or ''),
                        }
                        bp_tgt = bpart_targets.get((sp_name, bp_name))
                        if bp_tgt is None:
                            bp_tgt = targets_map.get(bp_name)
                        bp_info = bpart_meta.get((sp_name, bp_name)) or descriptions.get(bp_name) or {}
                        bpart_rows.append(
                            self._make_row(bp_name, bp_new, db_res.get(bp_name), bp_tgt, 'bpart', bp_info.get('description', ''), bp_info.get('dimension', ''), bp_info.get('part_number', ''))
                        )

                    bpart_rows.sort(key=lambda r: (bpart_meta.get((sp_name, r['key'])) or {}).get('sort_order', spart_order.get(r['key'], 9999)))
                    sp_row['bparts'] = bpart_rows
                    spart_groups.append(sp_row)

                # Добираем пустые SPart из license_details, для которых задан Target > 0, вместе с их BPart
                if full_list:
                    bparts_by_parent = {}
                    for it_fl in full_list:
                        if it_fl.get('type') == 'bpart' and it_fl.get('parent'):
                            bparts_by_parent.setdefault(it_fl['parent'], []).append(it_fl)

                    for it_fl in full_list:
                        if it_fl.get('type') != 'spart':
                            continue
                        sp_name = it_fl.get('name')
                        if not sp_name or sp_name in used_keys:
                            continue
                        sp_tgt = targets_map.get(sp_name)
                        if sp_tgt is None or sp_tgt <= 0:
                            continue

                        used_keys.add(sp_name)
                        sp_row = self._make_row(
                            sp_name, None, db_res.get(sp_name), sp_tgt, 'spart', it_fl.get('description', ''), it_fl.get('dimension', ''), it_fl.get('part_number', '')
                        )
                        bpart_rows = []
                        for bp_fl in bparts_by_parent.get(sp_name, []):
                            bp_name = bp_fl.get('name')
                            if not bp_name:
                                continue
                            used_keys.add(bp_name)
                            bp_tgt = bpart_targets.get((sp_name, bp_name))
                            if bp_tgt is None:
                                bp_tgt = targets_map.get(bp_name)
                            bpart_rows.append(
                                self._make_row(
                                    bp_name, None, db_res.get(bp_name), bp_tgt, 'bpart', bp_fl.get('description', ''), bp_fl.get('dimension', ''), bp_fl.get('part_number', '')
                                )
                            )
                        bpart_rows.sort(
                            key=lambda r: (bpart_meta.get((sp_name, r['key'])) or {}).get('sort_order', spart_order.get(r['key'], 9999))
                        )
                        sp_row['bparts'] = bpart_rows
                        spart_groups.append(sp_row)

            elif full_list and any(it.get('type') == 'spart' for it in full_list):
                # Сценарий DAT: в самой лицензии SPart нет, структура SPart -> BPart задана в license_details
                from modules.capacity_mapper import roundup
                bp_by_parent = {}
                for it_fl in full_list:
                    if it_fl.get('type') == 'bpart' and it_fl.get('parent'):
                        bp_by_parent.setdefault(it_fl['parent'], []).append(it_fl)

                for it_fl in full_list:
                    if it_fl.get('type') != 'spart':
                        continue
                    sp_name = it_fl.get('name')
                    if not sp_name or sp_name in used_keys:
                        continue
                    sp_tgt = targets_map.get(sp_name)
                    children_fl = bp_by_parent.get(sp_name, [])

                    bpart_rows = []
                    main_bp_name = None
                    for bp_fl in children_fl:
                        bp_name = bp_fl.get('name')
                        if not bp_name:
                            continue
                        if bp_fl.get('is_main_for_spart'):
                            main_bp_name = bp_name
                        bp_tgt = bpart_targets.get((sp_name, bp_name))
                        if bp_tgt is None:
                            bp_tgt = targets_map.get(bp_name)
                        bpart_rows.append(
                            self._make_row(
                                bp_name, new_res.get(bp_name), db_res.get(bp_name), bp_tgt, 'bpart', bp_fl.get('description', ''), bp_fl.get('dimension', ''), bp_fl.get('part_number', '')
                            )
                        )

                    bpart_rows.sort(
                        key=lambda r: (bpart_meta.get((sp_name, r['key'])) or {}).get('sort_order', spart_order.get(r['key'], 9999))
                    )

                    def _calc_spart_agg(res_map, rows_field_tot, rows_field_perm, rows_field_dated):
                        agg = None
                        if main_bp_name and main_bp_name in res_map:
                            agg = dict(res_map[main_bp_name])
                        elif bpart_rows:
                            tot = sum((r[rows_field_tot] or 0) for r in bpart_rows)
                            perm = sum((r[rows_field_perm] or 0) for r in bpart_rows)
                            dated = sum((r[rows_field_dated] or 0) for r in bpart_rows)
                            if tot > 0 or perm > 0 or dated > 0:
                                dates_set = sorted({str(b.get('valid_date') or '').strip() for b in bparts_rows if str(b.get('valid_date') or '').strip() and str(b.get('valid_date') or '').strip().upper() != 'PERMANENT'})
                                agg = {'total': tot, 'permanent': perm, 'dated': dated, 'valid_date': ', '.join(dates_set)}
                        coeff = it_fl.get('spart_coeff')
                        if coeff and agg:
                            try:
                                c_f = float(coeff)
                                agg['total'] = roundup((agg.get('total') or 0) * c_f, 0)
                                agg['permanent'] = roundup((agg.get('permanent') or 0) * c_f, 0)
                                agg['dated'] = roundup((agg.get('dated') or 0) * c_f, 0)
                            except (ValueError, TypeError):
                                pass
                        return agg

                    sp_new = _calc_spart_agg(new_res, 'new_total', 'new_perm', 'new_dated')
                    sp_db = db_res.get(sp_name) or _calc_spart_agg(db_res, 'db_total', 'db_perm', 'db_dated')

                    has_any_val = (sp_new is not None and (sp_new.get('total') or 0) > 0) or any((r['new_total'] or 0) > 0 for r in bpart_rows)
                    has_any_tgt = (sp_tgt is not None and sp_tgt > 0) or any((r['target_val'] is not None and r['target_val'] > 0) for r in bpart_rows)
                    if not (has_any_val or has_any_tgt):
                        continue

                    used_keys.add(sp_name)
                    for r in bpart_rows:
                        used_keys.add(r['key'])
                    sp_row = self._make_row(sp_name, sp_new, sp_db, sp_tgt, 'spart', it_fl.get('description', ''), it_fl.get('dimension', ''), it_fl.get('part_number', ''))
                    sp_row['bparts'] = bpart_rows
                    spart_groups.append(sp_row)

            for sg in spart_groups:
                sg['section'] = section_map.get(sg['key'], '')

            spart_groups.sort(key=lambda r: spart_order.get(r['key'], 9999))

            # Остальные ключи (для .dat, orphan_bparts и недостающих Target > 0; без хвоста старой БД)
            flat_rows = []
            tgt_nonzero_keys = {k for k, v in targets_map.items() if v is not None and v > 0}
            all_remaining = sorted((set(new_res.keys()) | tgt_nonzero_keys) - used_keys, key=lambda k: (spart_order.get(k, 9999), k))
            for key in all_remaining:
                flat_rows.append(
                    self._make_row(key, new_res.get(key), db_res.get(key), targets_map.get(key), 'flat', (descriptions.get(key) or {}).get('description', ''), (descriptions.get(key) or {}).get('dimension', ''), (descriptions.get(key) or {}).get('part_number', ''))
                )
            for fr in flat_rows:
                fr['section'] = section_map.get(fr['key'], '')

            # Подсчёт статистики
            all_check_rows = []
            for sg in spart_groups:
                all_check_rows.append(sg)
                all_check_rows.extend(sg['bparts'])
            all_check_rows.extend(flat_rows)

            changes_count = sum(1 for r in all_check_rows if r['delta_total'] != 0)
            shortage_count = sum(1 for r in all_check_rows if r['status'] == 'shortage')
            targets_checked = sum(1 for r in all_check_rows if r['target_val'] is not None)

            if f['status'] == 'error' or shortage_count > 0:
                severity = 'red'
            elif f['status'] == 'unknown_esn' or targets_checked == 0:
                severity = 'yellow'
            else:
                severity = 'green'

            items.append({
                'id': fid,
                'original_name': f['original_name'],
                'ext': f['ext'],
                'esn': esn or '—',
                'lsn': f.get('lsn') or '—',
                'product': f.get('product') or '',
                'node': f.get('node') or '',
                'version': f.get('version') or '',
                'valid_date': f.get('valid_date') or '',
                'create_time': f.get('create_time') or '',
                'domain': f.get('domain') or 'unknown',
                'sub_domain': f.get('sub_domain') or '',
                'city': f.get('city') or '',
                'city_full': f.get('city_full') or f.get('city') or 'Без города',
                'ne_type': f.get('ne_type') or f.get('product') or 'NE',
                'site': f.get('site') or f.get('node') or f['original_name'],
                'status': f['status'],
                'status_text': f['status_text'],
                'selected': f.get('selected', True),
                'db_latest': db_lic_meta,
                'severity': severity,
                'changes_count': changes_count,
                'shortage_count': shortage_count,
                'total_params': len(all_check_rows),
                'spart_groups': spart_groups,
                'flat_rows': flat_rows,
                'city_targets': self._load_city_targets_summary(target_op, f.get('ne_type'), f.get('city')),
                'new_name': self._compute_planned_name(f, target_op),
            })

        domains_summary = {}
        for it in items:
            d = it['domain']
            if d not in domains_summary:
                domains_summary[d] = {'name': d, 'count': 0, 'red': 0, 'yellow': 0, 'green': 0}
            domains_summary[d]['count'] += 1
            domains_summary[d][it['severity']] += 1

        return {
            'operator': operator,
            'domains': sorted(domains_summary.values(), key=lambda x: x['name']),
            'items': items,
            'total_shortages': sum(it['shortage_count'] for it in items),
        }

    def _get_operator_storage_base(self, operator):
        from modules.config_store import load_config
        cfg = load_config(force_reload=True) or {}
        ops = cfg.get('operators')
        op_cfg = {}

        if isinstance(ops, dict):
            op_cfg = ops.get(operator) or {}
        elif isinstance(ops, list):
            target = (operator or '').strip().lower()
            for item in ops:
                if not isinstance(item, dict):
                    continue
                keys = [str(item.get(k) or '').strip().lower() for k in ('id', 'code', 'key', 'name', 'operator')]
                if target and target in keys:
                    op_cfg = item
                    break

        for key in ('network_storage_path', 'network_path', 'storage_path', 'remote_base', 'path', 'local_path'):
            val = op_cfg.get(key)
            if val:
                return val

        root_net = cfg.get('network_storage_path') or cfg.get('network_path')
        if root_net:
            return os.path.join(root_net, operator) if operator else root_net

        return os.path.join('data', 'licenses', operator or 'default')

    def _build_lic_dict_for_reorg(self, entry, operator):
        from modules.bulk_reorganizer import _calc_year_folder
        valid_date = entry.get('valid_date') or ''
        year = _calc_year_folder(valid_date, None)
        ext = (entry.get('ext') or '').lstrip('.')
        return {
            'filename': entry.get('original_name') or '',
            'file_path': entry.get('saved_path') or '',
            'file_type': ext,
            'operator': operator or entry.get('mapped_operator') or '',
            'domain': entry.get('domain') or 'unknown',
            'sub_domain': entry.get('sub_domain') or '',
            'ne_type': entry.get('ne_type') or '',
            'city': entry.get('city') or '',
            'city_full': entry.get('city_full') or entry.get('city') or '',
            'site': entry.get('site') or '',
            'version': entry.get('version') or '',
            'valid_date': valid_date,
            'create_time': entry.get('create_time') or '',
            'year': year,
            'lsn': entry.get('lsn') or '',
            'esn': entry.get('esn') or '',
        }

    def preview_import_paths(self, operator=None):
        from modules.config_store import load_config
        from modules.bulk_reorganizer import _target_path

        load_config(force_reload=True)
        remote_base = self._get_operator_storage_base(operator)
        norm_base = os.path.normpath(remote_base)
        op_clean = (operator or '').strip()
        reorg_base = norm_base
        if op_clean and os.path.basename(norm_base).lower() == op_clean.lower():
            parent_base = os.path.dirname(norm_base)
            if parent_base:
                reorg_base = parent_base

        state_data = self.get_state(operator=operator)
        files = [f for f in state_data.get('files', []) if f.get('selected')]

        preview_items = []
        for f in files:
            lic_dict = self._build_lic_dict_for_reorg(f, operator)
            try:
                target_full = _target_path(reorg_base, lic_dict, 'both')
                if reorg_base != norm_base:
                    t_norm = os.path.normcase(os.path.normpath(target_full))
                    b_norm = os.path.normcase(norm_base)
                    if not (t_norm == b_norm or t_norm.startswith(b_norm + os.sep)):
                        target_full = _target_path(norm_base, lic_dict, 'both')
            except Exception:
                target_full = os.path.join(norm_base, f['original_name'])

            target_dir = os.path.dirname(target_full)
            new_name = os.path.basename(target_full)
            t_dir_norm = os.path.normpath(target_dir)
            if os.path.normcase(t_dir_norm).startswith(os.path.normcase(norm_base)):
                rel_dir = os.path.relpath(t_dir_norm, norm_base)
            else:
                rel_dir = t_dir_norm
            exists_on_disk = os.path.exists(target_full)

            missing_fields = []
            if not f.get('ne_type'):
                missing_fields.append('ne_type')
            if not f.get('city'):
                missing_fields.append('city')

            preview_items.append({
                'id': f['id'],
                'original_name': f['original_name'],
                'domain': f.get('domain') or 'unknown',
                'city_full': f.get('city_full') or f.get('city') or '',
                'site': f.get('site') or '',
                'target_dir': target_dir,
                'rel_dir': rel_dir,
                'new_name': new_name,
                'target_full': target_full,
                'exists_on_disk': exists_on_disk,
                'missing_fields': missing_fields,
            })

        return {
            'operator': operator,
            'remote_base': remote_base,
            'selected_count': len(preview_items),
            'items': preview_items,
        }

    def commit_batch(self, operator=None, copy_files=True, modified_by='web_upload'):
        from modules.database import save_licenses_batch
        from modules.bulk_reorganizer import _calc_year_folder

        preview = self.preview_import_paths(operator=operator)
        state = self._load_state()
        files_by_id = {f['id']: f for f in state.get('files', [])}

        import uuid as _uuid
        from datetime import datetime as _dt
        upload_batch_id = f"{_dt.now().strftime('%Y-%m-%d_%H%M')}_{_uuid.uuid4().hex[:4].upper()}"
        licenses_to_save = []
        committed_ids = []
        copied_count = 0
        file_errors = []

        for item in preview.get('items', []):
            fid = item['id']
            f = files_by_id.get(fid)
            if not f:
                continue

            src_path = f.get('saved_path')
            if not src_path or not os.path.exists(src_path):
                file_errors.append(f"{f['original_name']}: файл не найден в staging")
                continue

            final_path = src_path
            final_name = f['original_name']

            if copy_files:
                try:
                    os.makedirs(item['target_dir'], exist_ok=True)
                    shutil.copy2(src_path, item['target_full'])
                    final_path = item['target_full']
                    final_name = item['new_name']
                    copied_count += 1
                except Exception as e:
                    file_errors.append(f"{f['original_name']}: ошибка копирования ({e})")
                    continue

            try:
                ext = f.get('ext', '').lower()
                parsed = parse_dat_license(final_path) if ext == '.dat' else parse_xml_license(final_path)
                if not isinstance(parsed, dict):
                    raise ValueError('Пустой результат парсинга')

                valid_date = parsed.get('valid_date') or f.get('valid_date') or ''
                year = _calc_year_folder(valid_date, None)

                lic_record = dict(parsed)
                lic_record['operator'] = operator or f.get('mapped_operator') or ''
                lic_record['domain'] = f.get('domain') or 'unknown'
                lic_record['ne_type'] = f.get('ne_type') or parsed.get('product') or 'UNKNOWN'
                lic_record['city'] = f.get('city') or 'UNKNOWN'
                lic_record['city_full'] = f.get('city_full') or f.get('city') or ''
                lic_record['site'] = f.get('site') or parsed.get('node') or ''
                lic_record['year'] = year
                lic_record['filename'] = final_name
                lic_record['file_path'] = final_path
                lic_record['local_path'] = final_path
                lic_record['upload_batch_id'] = upload_batch_id

                licenses_to_save.append(lic_record)
                committed_ids.append(fid)
            except Exception as e:
                file_errors.append(f"{f['original_name']}: ошибка подготовки для БД ({e})")

        saved_count, db_errors = save_licenses_batch(licenses_to_save, modified_by=modified_by)

        if saved_count > 0:
            for fid in committed_ids:
                self.remove_file(fid, operator=operator)

        return {
            'saved': saved_count,
            'db_errors': db_errors,
            'copied': copied_count,
            'file_errors': file_errors,
            'upload_batch_id': upload_batch_id,
            'state': self.get_state(operator=operator),
        }


    def list_db_licenses(self, operator=None, only_web_upload=False):
        from modules.database import get_connection

        conn = get_connection()
        conn.row_factory = None
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(licenses)")
        cols = [row[1] for row in cur.fetchall()]
        has_city_full = 'city_full' in cols

        select_cols = [
            'id', 'operator', 'domain', 'ne_type', 'city',
            'city_full' if has_city_full else "'' AS city_full",
            'site', 'year', 'filename', 'lsn', 'esn', 'version',
            'create_time', 'valid_date', 'last_modified', 'modified_by', 'local_path'
        ]
        sql = f"SELECT {', '.join(select_cols)} FROM licenses WHERE 1=1"
        params = []
        if operator:
            sql += " AND LOWER(COALESCE(operator, '')) = LOWER(?)"
            params.append(operator)
        if only_web_upload:
            sql += " AND modified_by = 'web_upload'"
        sql += " ORDER BY COALESCE(last_modified, '') DESC, id DESC LIMIT 1000"

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        items = []
        domains = set()
        for r in rows:
            dom = r[2] or 'unknown'
            domains.add(dom)
            local_path = r[16] or ''
            items.append({
                'id': r[0],
                'operator': r[1] or '',
                'domain': dom,
                'ne_type': r[3] or '',
                'city': r[4] or '',
                'city_full': r[5] or r[4] or '',
                'site': r[6] or '',
                'year': r[7] or '',
                'filename': r[8] or '',
                'lsn': r[9] or '',
                'esn': r[10] or '',
                'version': r[11] or '',
                'create_time': r[12] or '',
                'valid_date': r[13] or '',
                'last_modified': r[14] or '',
                'modified_by': r[15] or '',
                'local_path': local_path,
                'file_exists': bool(local_path and os.path.exists(local_path)),
            })
        return {
            'items': items,
            'domains': sorted(domains),
            'total': len(items),
        }

    def load_from_db_licenses(self, license_ids, operator=None, clear_first=True):
        import uuid
        from modules.database import get_connection

        ids = [int(x) for x in (license_ids or []) if str(x).isdigit()]
        if not ids:
            return {'error': 'Не выбраны лицензии для сравнения'}

        conn = get_connection()
        cur = conn.cursor()
        placeholders = ','.join('?' for _ in ids)
        cols = ['id', 'operator', 'domain', 'city', 'city_full', 'site', 'year', 'ne_type', 'version', 'filename', 'local_path']
        cur.execute(
            f"SELECT {', '.join(cols)} FROM licenses WHERE id IN ({placeholders})",
            ids
        )
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()

        if clear_first:
            self.clear_session()

        state = self._load_state()
        files = state.get('files', [])
        loaded = 0
        errors = []
        base_dir = self._get_operator_storage_base(operator)
        filename_index = {}

        for lic in rows:
            lic_id = lic['id']
            filename = lic.get('filename')
            src_path = self._resolve_license_file_path(lic, base_dir, filename_index)
            if not src_path or not os.path.isfile(src_path):
                errors.append(f"{filename or lic_id}: файл не найден на шаре ({base_dir or 'базовая папка не задана'})")
                continue
            orig_name = filename or os.path.basename(src_path)
            if not self._is_allowed(orig_name):
                errors.append(f"{orig_name}: неподдерживаемое расширение")
                continue
            try:
                os.makedirs(STAGING_ROOT, exist_ok=True)
                ext = os.path.splitext(orig_name)[1].lower()
                dst_path = os.path.join(STAGING_ROOT, f"{uuid.uuid4().hex}{ext}")
                shutil.copy2(src_path, dst_path)
                entry = self._build_file_entry(orig_name, dst_path, operator=operator)
                files.append(entry)
                loaded += 1
            except Exception as e:
                errors.append(f"{orig_name}: {e}")

        state['files'] = files
        self._save_state(state)
        return {
            'loaded': loaded,
            'errors': errors,
            'state': self.get_state(operator=operator),
        }

    def copy_db_licenses_to_new_folder(self, license_ids, operator=None):
        import uuid
        from datetime import datetime
        from modules.database import get_connection

        ids = [int(x) for x in (license_ids or []) if str(x).isdigit()]
        if not ids:
            return {'error': 'Не выбраны лицензии для копирования'}

        conn = get_connection()
        cur = conn.cursor()
        placeholders = ','.join('?' for _ in ids)
        cur.execute(
            f"SELECT id, filename, local_path FROM licenses WHERE id IN ({placeholders})",
            ids
        )
        rows = cur.fetchall()
        conn.close()

        base_dir = self._get_operator_storage_base(operator)
        copy_id = uuid.uuid4().hex[:6].upper()
        folder_name = f"{datetime.now().strftime('%Y-%m-%d')}_{copy_id}"
        target_dir = os.path.join(base_dir, '_New-licenses', folder_name)
        os.makedirs(target_dir, exist_ok=True)

        copied = 0
        errors = []
        for lic_id, filename, local_path in rows:
            if not local_path or not os.path.exists(local_path):
                errors.append(f"{filename or lic_id}: файл не найден на диске")
                continue
            try:
                dst_name = filename or os.path.basename(local_path)
                dst_path = os.path.join(target_dir, dst_name)
                if os.path.exists(dst_path):
                    stem, ext = os.path.splitext(dst_name)
                    dst_path = os.path.join(target_dir, f"{stem}_{lic_id}{ext}")
                shutil.copy2(local_path, dst_path)
                copied += 1
            except Exception as e:
                errors.append(f"{filename or lic_id}: {e}")

        return {
            'copied': copied,
            'copy_id': copy_id,
            'target_dir': target_dir,
            'errors': errors,
        }


    def _ensure_batch_col(self, conn):
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(licenses)")
        cols = [c[1] for c in cur.fetchall()]
        if 'upload_batch_id' not in cols:
            cur.execute("ALTER TABLE licenses ADD COLUMN upload_batch_id TEXT")
            conn.commit()
            cols.append('upload_batch_id')
        return cols

    def list_upload_sessions(self, operator=None):
        from modules.database import get_connection

        conn = get_connection()
        self._ensure_batch_col(conn)
        cur = conn.cursor()

        sql = """
            SELECT
                CASE
                    WHEN COALESCE(upload_batch_id, '') != '' THEN upload_batch_id
                    ELSE 'DATE:' || SUBSTR(COALESCE(last_modified, 'unknown'), 1, 10) || '|' || COALESCE(modified_by, 'system')
                END AS sess_id,
                COUNT(*) AS cnt,
                MAX(COALESCE(last_modified, '')) AS max_dt,
                GROUP_CONCAT(DISTINCT COALESCE(domain, 'unknown')) AS domains,
                MAX(COALESCE(modified_by, '')) AS src
            FROM licenses
            WHERE 1=1
        """
        params = []
        if operator:
            sql += " AND LOWER(COALESCE(operator, '')) = LOWER(?)"
            params.append(operator)
        sql += " GROUP BY sess_id ORDER BY max_dt DESC LIMIT 100"

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        sessions = []
        for sess_id, cnt, max_dt, domains_str, src in rows:
            is_batch = not str(sess_id).startswith('DATE:')
            if is_batch:
                label = f"Сессия {sess_id}"
            else:
                parts = str(sess_id)[5:].split('|')
                label = f"Загрузка за {parts[0]} ({parts[1] if len(parts) > 1 else 'system'})"
            sessions.append({
                'session_id': sess_id,
                'label': label,
                'is_batch': is_batch,
                'count': cnt,
                'last_modified': max_dt,
                'domains': [d for d in (domains_str or '').split(',') if d],
                'modified_by': src or 'system',
            })
        return {'sessions': sessions}

    def _fetch_licenses_for_sessions(self, session_ids, operator=None):
        from modules.database import get_connection

        if not session_ids:
            return []
        conn = get_connection()
        cols = self._ensure_batch_col(conn)
        has_city_full = 'city_full' in cols
        has_sub_domain = 'sub_domain' in cols
        cur = conn.cursor()

        select_cols = [
            'id', 'operator', 'domain', 'ne_type', 'city',
            'city_full' if has_city_full else "'' AS city_full",
            'site', 'year', 'filename', 'lsn', 'esn', 'version',
            'create_time', 'valid_date', 'last_modified', 'modified_by', 'local_path',
            'upload_batch_id',
            'sub_domain' if has_sub_domain else "'' AS sub_domain"
        ]
        sess_expr = "CASE WHEN COALESCE(upload_batch_id, '') != '' THEN upload_batch_id ELSE 'DATE:' || SUBSTR(COALESCE(last_modified, 'unknown'), 1, 10) || '|' || COALESCE(modified_by, 'system') END"
        placeholders = ','.join('?' for _ in session_ids)
        sql = f"SELECT {', '.join(select_cols)} FROM licenses WHERE ({sess_expr}) IN ({placeholders})"
        params = list(session_ids)
        if operator:
            sql += " AND LOWER(COALESCE(operator, '')) = LOWER(?)"
            params.append(operator)
        sql += " ORDER BY COALESCE(domain, ''), COALESCE(city, ''), COALESCE(site, ''), id DESC"

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        result = []
        for r in rows:
            result.append({
                'id': r[0],
                'operator': r[1] or operator or '',
                'domain': r[2] or 'unknown',
                'ne_type': r[3] or '',
                'city': r[4] or '',
                'city_full': r[5] or r[4] or '',
                'site': r[6] or '',
                'year': r[7] or '',
                'filename': r[8] or '',
                'lsn': r[9] or '',
                'esn': r[10] or '',
                'version': r[11] or '',
                'create_time': r[12] or '',
                'valid_date': r[13] or '',
                'last_modified': r[14] or '',
                'modified_by': r[15] or '',
                'local_path': r[16] or '',
                'upload_batch_id': r[17] or '',
                'sub_domain': r[18] or '',
            })
        return result

    def _build_package_rel_dir(self, lic):
        from modules.config_store import get_folder_structure_for_domain
        from modules.bulk_reorganizer import _render_folder_segment, _clean_part

        domain = lic.get('domain') or 'UNMAPPED'
        sub_domain = _clean_part(lic.get('sub_domain'))
        op_name = lic.get('operator') or 'Unknown'
        path_values = {
            'operator': op_name,
            'domain': domain,
            'sub_domain': sub_domain or 'Unknown',
            'ne_type': lic.get('ne_type') or 'Unknown',
            'city': lic.get('city') or 'Unknown',
            'site': lic.get('site') or 'Unknown',
            'year': '',
            'version': lic.get('version') or 'unknown',
            'lsn': lic.get('lsn') or '',
            'esn': lic.get('esn') or '',
        }
        levels = get_folder_structure_for_domain(domain, operator=op_name, has_sub_domain=bool(sub_domain))
        parts = []
        for lvl in levels:
            low = str(lvl).strip().lower()
            if '{year}' in low or '{operator}' in low or low in ('year', 'operator'):
                continue
            seg = _render_folder_segment(lvl, path_values)
            if seg:
                parts.append(seg)
        return os.path.join(*parts) if parts else ''

    def _next_package_dir(self, operator, folder_comment=''):
        import re as _re
        from datetime import datetime

        base_dir = self._get_operator_storage_base(operator)
        root_new = os.path.join(base_dir, '_New-licenses')
        date_str = datetime.now().strftime('%Y-%m-%d')
        clean_comment = _re.sub(r'[^A-Za-z0-9А-Яа-яЁё._-]+', '_', (folder_comment or '').strip()).strip('_')

        idx = 1
        while True:
            suffix = f"_{clean_comment}" if clean_comment else ""
            folder_name = f"{date_str}_{idx:02d}{suffix}"
            cand = os.path.join(root_new, folder_name)
            if not os.path.exists(cand):
                return cand, folder_name
            idx += 1

    def _resolve_license_file_path(self, lic, base_dir, filename_index=None):
        import time
        raw_src = (lic.get('local_path') or '').strip()
        fname = (lic.get('filename') or '').strip()

        candidates = []
        if raw_src:
            norm_src = os.path.normpath(raw_src)
            candidates.append(norm_src)
            if not os.path.isabs(norm_src) and base_dir:
                candidates.append(os.path.normpath(os.path.join(base_dir, norm_src)))
                parent_base = os.path.dirname(os.path.normpath(base_dir))
                if parent_base:
                    candidates.append(os.path.normpath(os.path.join(parent_base, norm_src)))

        for cand in candidates:
            if cand and os.path.isfile(cand):
                return cand

        if fname and base_dir:
            norm_base = os.path.normpath(base_dir)
            if os.path.isdir(norm_base):
                low_target = fname.lower()
                if filename_index is not None and low_target in filename_index:
                    return filename_index[low_target]

                if not hasattr(self, '_share_index_cache'):
                    self._share_index_cache = {}
                cached = self._share_index_cache.get(norm_base)
                now = time.time()
                if cached and (now - cached['ts'] < 60):
                    idx = cached['index']
                else:
                    idx = {}
                    for root, _, files in os.walk(norm_base):
                        for fn in files:
                            low = fn.lower()
                            if low not in idx:
                                idx[low] = os.path.join(root, fn)
                    self._share_index_cache[norm_base] = {'ts': now, 'index': idx}

                if filename_index is not None:
                    filename_index.update(idx)
                if low_target in idx:
                    return idx[low_target]

        return raw_src

    def preview_package_export(self, session_ids, operator=None, mode='structure', folder_comment=''):
        lics = self._fetch_licenses_for_sessions(session_ids, operator=operator)
        target_dir, folder_name = self._next_package_dir(operator, folder_comment)

        base_dir = self._get_operator_storage_base(operator)
        filename_index = {}
        used_rel = set()
        items = []
        missing_count = 0
        for lic in lics:
            src = self._resolve_license_file_path(lic, base_dir, filename_index)
            exists = bool(src and os.path.isfile(src))
            if not exists:
                missing_count += 1
            fname = lic.get('filename') or (os.path.basename(src) if src else f"license_{lic['id']}.dat")
            rel_dir = '' if mode == 'flat' else self._build_package_rel_dir(lic)
            rel_path = os.path.join(rel_dir, fname) if rel_dir else fname

            if rel_path.lower() in used_rel:
                stem, ext = os.path.splitext(fname)
                tag = lic.get('lsn') or str(lic['id'])
                fname = f"{stem}_{tag}{ext}"
                rel_path = os.path.join(rel_dir, fname) if rel_dir else fname
            used_rel.add(rel_path.lower())

            items.append({
                'id': lic['id'],
                'domain': lic['domain'],
                'city_full': lic['city_full'],
                'city': lic['city'],
                'site': lic['site'],
                'ne_type': lic['ne_type'],
                'version': lic['version'],
                'lsn': lic['lsn'],
                'esn': lic['esn'],
                'create_time': lic['create_time'],
                'valid_date': lic['valid_date'],
                'last_modified': lic['last_modified'],
                'filename': fname,
                'local_path': src,
                'file_exists': exists,
                'rel_dir': rel_dir.replace('\\', '/'),
                'rel_path': rel_path.replace('\\', '/'),
            })

        return {
            'target_dir': target_dir,
            'folder_name': folder_name,
            'mode': mode,
            'total': len(items),
            'missing_count': missing_count,
            'items': items,
        }

    def export_package(self, session_ids, operator=None, mode='structure', folder_comment='',
                       include_html=True, include_zip=True, include_xlsx=False, html_content=None):
        import zipfile

        preview = self.preview_package_export(session_ids, operator=operator, mode=mode, folder_comment=folder_comment)
        items = preview['items']
        if not items:
            return {'error': 'Нет лицензий в выбранных сессиях'}

        target_dir = preview['target_dir']
        os.makedirs(target_dir, exist_ok=True)

        copied = 0
        errors = []
        for it in items:
            if not it['file_exists']:
                errors.append(f"{it['filename']}: исходный файл не найден")
                continue
            try:
                dst = os.path.join(target_dir, *it['rel_path'].split('/'))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(it['local_path'], dst)
                copied += 1
            except Exception as e:
                errors.append(f"{it['filename']}: {e}")

        html_path = ''
        if include_html and html_content:
            html_path = os.path.join(target_dir, 'license_package_report.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

        xlsx_path = ''
        if include_xlsx:
            try:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Licenses'
                headers = ['Domain', 'City', 'Site', 'NE Type', 'Version', 'ESN', 'LSN', 'Created', 'Valid Until', 'Uploaded', 'Relative Path']
                ws.append(headers)
                def _date_only(val):
                    s = str(val or '').strip()
                    if not s:
                        return ''
                    return s.split('T')[0].split(' ')[0]

                for it in items:
                    ws.append([
                        it['domain'], it['city_full'] or it['city'], it['site'], it['ne_type'],
                        it['version'], it['esn'], it['lsn'],
                        _date_only(it['create_time']), it['valid_date'],
                        _date_only(it['last_modified']), it['rel_path']
                    ])

                from openpyxl.utils import get_column_letter
                for col_idx, col_name in enumerate(headers, 1):
                    if col_name == 'ESN':
                        continue
                    max_len = max(
                        (len(str(ws.cell(row=r_idx, column=col_idx).value or '')) for r_idx in range(1, ws.max_row + 1)),
                        default=len(col_name)
                    )
                    ws.column_dimensions[get_column_letter(col_idx)].width = max_len + 3

                xlsx_path = os.path.join(target_dir, 'manifest.xlsx')
                wb.save(xlsx_path)
            except Exception as e:
                errors.append(f"manifest.xlsx: {e}")

        zip_path = ''
        if include_zip:
            try:
                zip_path = target_dir + '.zip'
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(target_dir):
                        for fn in files:
                            full_p = os.path.join(root, fn)
                            arc_p = os.path.relpath(full_p, target_dir)
                            zf.write(full_p, arc_p)
            except Exception as e:
                errors.append(f"ZIP: {e}")

        return {
            'target_dir': target_dir,
            'folder_name': preview['folder_name'],
            'copied': copied,
            'total': len(items),
            'html_path': html_path,
            'xlsx_path': xlsx_path,
            'zip_path': zip_path,
            'errors': errors,
        }
