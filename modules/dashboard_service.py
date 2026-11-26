# modules/dashboard_service.py
from datetime import datetime
from collections import defaultdict
from modules.database import get_connection, get_unique_esn_licenses, get_all_licenses


def _norm_esn(val):
    return str(val or "").strip().upper()


def _parse_iso_date(val):
    if not val:
        return None
    s = str(val).strip()
    if not s or s.upper() in ("PERMANENT", "UNKNOWN", "NONE", "NULL"):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _collect_operator_state(operator, op_title=None, pending_sync=0):
    """
    Собирает полную аналитику по БД выбранного оператора:
    - активные лицензии (уникальные ESN, последняя версия)
    - все лицензии (включая историю)
    - маппинг ESN из таблицы esn_mapping
    - классификация Permanent / Fixterm / Permanent + Fixterm
    - сроки действия (Expired, <=30d, 31-90d)
    """
    today = datetime.now().date()
    active_licenses = get_unique_esn_licenses(operator)
    all_licenses = get_all_licenses(operator=operator)

    conn = get_connection()
    cursor = conn.cursor()

    op_candidates = {str(operator or "").strip().lower()}
    if op_title:
        op_candidates.add(str(op_title).strip().lower())
    placeholders = ",".join("?" for _ in op_candidates)
    cursor.execute(
        f"""
        SELECT esn, lsn, operator, domain, sub_domain, ne_type, city, site
        FROM esn_mapping
        WHERE LOWER(TRIM(COALESCE(operator, ''))) IN ({placeholders})
        """,
        tuple(op_candidates),
    )
    mapping_rows = cursor.fetchall()
    mapping_by_esn = {}
    for row in mapping_rows:
        esn_key = _norm_esn(row[0])
        if esn_key:
            mapping_by_esn[esn_key] = {
                "esn": row[0],
                "lsn": row[1] or "",
                "operator": row[2] or "",
                "domain": row[3] or "",
                "sub_domain": row[4] or "",
                "ne_type": row[5] or "",
                "city": row[6] or "",
                "site": row[7] or "",
            }

    active_ids = [lic["id"] for lic in active_licenses]
    perm_flags = defaultdict(lambda: {"perm": False, "fix": False})
    dated_items = defaultdict(list)

    if active_ids:
        id_ph = ",".join("?" for _ in active_ids)

        cursor.execute(
            f"""
            SELECT license_id, capacity_key, permanent_value, latest_date
            FROM capacity_aggregated
            WHERE license_id IN ({id_ph})
            """,
            tuple(active_ids),
        )
        for lic_id, cap_key, perm_val, latest_date in cursor.fetchall():
            if perm_val and perm_val > 0:
                perm_flags[lic_id]["perm"] = True
            dt = _parse_iso_date(latest_date)
            if dt:
                perm_flags[lic_id]["fix"] = True
                dated_items[lic_id].append((dt, cap_key or ""))

        cursor.execute(
            f"""
            SELECT license_id, capacity_key, valid_date
            FROM resources
            WHERE license_id IN ({id_ph})
            """,
            tuple(active_ids),
        )
        for lic_id, cap_key, vdate in cursor.fetchall():
            v_up = str(vdate or "").strip().upper()
            if v_up == "PERMANENT":
                perm_flags[lic_id]["perm"] = True
            else:
                dt = _parse_iso_date(vdate)
                if dt:
                    perm_flags[lic_id]["fix"] = True
                    dated_items[lic_id].append((dt, cap_key or ""))

    cursor.execute(
        """
        SELECT MAX(COALESCE(last_modified, create_time))
        FROM licenses
        WHERE operator = ?
        """,
        (operator,),
    )
    last_db_update_row = cursor.fetchone()
    last_db_update = (last_db_update_row[0] if last_db_update_row else None) or "—"
    conn.close()

    active_by_esn = {}
    enriched_active = []
    buckets = {
        "permanent": [],
        "fixterm": [],
        "permanent_fixterm": [],
        "unknown_type": [],
        "expired": [],
        "expiring_30": [],
        "expiring_90": [],
    }

    for lic in active_licenses:
        lic_id = lic["id"]
        esn_key = _norm_esn(lic.get("esn"))
        flags = perm_flags[lic_id]
        has_perm = flags["perm"]
        has_fix = flags["fix"]

        if not has_perm and not has_fix:
            vd_up = str(lic.get("valid_date") or "").strip().upper()
            if vd_up == "PERMANENT":
                has_perm = True
            elif _parse_iso_date(lic.get("valid_date")):
                has_fix = True

        if has_perm and has_fix:
            lic_kind = "Permanent + Fixterm"
            kind_key = "permanent_fixterm"
        elif has_perm:
            lic_kind = "Permanent"
            kind_key = "permanent"
        elif has_fix:
            lic_kind = "Fixterm"
            kind_key = "fixterm"
        else:
            lic_kind = "Unknown"
            kind_key = "unknown_type"

        dates_list = dated_items.get(lic_id, [])
        if not dates_list:
            fallback_dt = _parse_iso_date(lic.get("valid_date"))
            if fallback_dt:
                dates_list = [(fallback_dt, "")]

        nearest_dt = min((d for d, _ in dates_list), default=None)
        days_left = (nearest_dt - today).days if nearest_dt else None

        fname = lic.get("filename") or ""
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

        item = {
            "id": lic_id,
            "esn": lic.get("esn") or "",
            "esn_norm": esn_key,
            "lsn": lic.get("lsn") or "",
            "ne_type": lic.get("ne_type") or "-",
            "city": lic.get("city") or "-",
            "site": lic.get("site") or "-",
            "year": lic.get("year") or "-",
            "domain": lic.get("domain") or "-",
            "product": lic.get("product") or "-",
            "version": lic.get("version") or "-",
            "filename": fname,
            "file_ext": ext,
            "valid_date": lic.get("valid_date") or "-",
            "nearest_expire": nearest_dt.isoformat() if nearest_dt else "PERMANENT",
            "days_left": days_left,
            "license_kind": lic_kind,
            "kind_key": kind_key,
            "in_mapping": esn_key in mapping_by_esn,
        }

        enriched_active.append(item)
        if esn_key:
            active_by_esn[esn_key] = item
        buckets[kind_key].append(item)

        if days_left is not None:
            if days_left < 0:
                buckets["expired"].append(item)
            elif days_left <= 30:
                buckets["expiring_30"].append(item)
            elif days_left <= 90:
                buckets["expiring_90"].append(item)

    mapped_esns = set(mapping_by_esn.keys())
    db_esns = set(active_by_esn.keys())
    covered_esns = mapped_esns & db_esns
    missing_esns = sorted(mapped_esns - db_esns)
    unmapped_esns = sorted(db_esns - mapped_esns)

    coverage_pct = round((len(covered_esns) / len(mapped_esns)) * 100, 1) if mapped_esns else 0.0

    missing_esn_rows = [mapping_by_esn[k] for k in missing_esns]
    covered_esn_rows = [active_by_esn[k] for k in sorted(covered_esns)]
    unmapped_esn_rows = [active_by_esn[k] for k in unmapped_esns]

    dat_count = sum(1 for l in all_licenses if (l.get("filename") or "").lower().endswith(".dat"))
    xml_count = sum(1 for l in all_licenses if (l.get("filename") or "").lower().endswith(".xml"))

    ne_stats = defaultdict(lambda: {"esn_count": 0, "perm": 0, "fix": 0, "both": 0, "risk": 0, "cities": set()})
    city_stats = defaultdict(lambda: {"esn_count": 0, "ne_types": set(), "sites": set(), "risk": 0})

    for item in enriched_active:
        ne = item["ne_type"]
        city = item["city"]
        ne_stats[ne]["esn_count"] += 1
        ne_stats[ne]["cities"].add(city)
        if item["kind_key"] == "permanent":
            ne_stats[ne]["perm"] += 1
        elif item["kind_key"] == "fixterm":
            ne_stats[ne]["fix"] += 1
        elif item["kind_key"] == "permanent_fixterm":
            ne_stats[ne]["both"] += 1
        if item["days_left"] is not None and item["days_left"] <= 30:
            ne_stats[ne]["risk"] += 1

        city_stats[city]["esn_count"] += 1
        city_stats[city]["ne_types"].add(ne)
        if item["site"] and item["site"] != "-":
            city_stats[city]["sites"].add(item["site"])
        if item["days_left"] is not None and item["days_left"] <= 30:
            city_stats[city]["risk"] += 1

    summary = {
        "unique_esn_count": len(enriched_active),
        "mapped_esn_count": len(mapped_esns),
        "covered_esn_count": len(covered_esns),
        "coverage_pct": coverage_pct,
        "missing_esn_count": len(missing_esns),
        "unmapped_esn_count": len(unmapped_esns),
        "total_licenses_count": len(all_licenses),
        "dat_count": dat_count,
        "xml_count": xml_count,
        "permanent_count": len(buckets["permanent"]),
        "fixterm_count": len(buckets["fixterm"]),
        "permanent_fixterm_count": len(buckets["permanent_fixterm"]),
        "unknown_type_count": len(buckets["unknown_type"]),
        "expired_count": len(buckets["expired"]),
        "expiring_30_count": len(buckets["expiring_30"]),
        "expiring_90_count": len(buckets["expiring_90"]),
        "ne_types_count": len([k for k in ne_stats.keys() if k != "-"]),
        "cities_count": len([k for k in city_stats.keys() if k != "-"]),
        "last_db_update": str(last_db_update)[:19].replace("T", " "),
        "pending_sync": pending_sync,
    }

    return {
        "summary": summary,
        "active": enriched_active,
        "all_licenses": all_licenses,
        "buckets": buckets,
        "missing_esn_rows": missing_esn_rows,
        "covered_esn_rows": covered_esn_rows,
        "unmapped_esn_rows": unmapped_esn_rows,
        "ne_stats": ne_stats,
        "city_stats": city_stats,
    }


def get_operator_dashboard_summary(operator, op_title=None, pending_sync=0):
    return _collect_operator_state(operator, op_title=op_title, pending_sync=pending_sync)["summary"]


def _format_license_records(operator, items):
    """Формирует строки в стиле таблицы 'Список лицензий' с возможностью открытия деталей."""
    records = []
    for i in items:
        lic_id = i.get("id")
        esn = i.get("esn") or ""
        detail_url = f"/{operator}/license_by_esn/{esn}" if esn else (f"/{operator}/license/{lic_id}" if lic_id else "")
        days_txt = "" if i.get("days_left") is None else str(i.get("days_left"))
        expire_disp = i.get("nearest_expire") or i.get("valid_date") or "-"
        if days_txt != "":
            expire_disp = f"{expire_disp} ({days_txt} дн.)"

        records.append({
            "id": lic_id,
            "ne_type": i.get("ne_type") or "-",
            "city": i.get("city") or "-",
            "site": i.get("site") or "-",
            "year": i.get("year") or "-",
            "lsn": i.get("lsn") or "-",
            "product": i.get("product") or "-",
            "version": i.get("version") or "-",
            "esn": esn or "-",
            "domain": i.get("domain") or "-",
            "license_kind": i.get("license_kind") or "-",
            "expire_disp": expire_disp,
            "filename": i.get("filename") or "-",
            "detail_url": detail_url,
        })
    return records


def get_dashboard_metric_details(operator, metric, op_title=None, pending_sync=0):
    state = _collect_operator_state(operator, op_title=op_title, pending_sync=pending_sync)
    list_url = f"/{operator}/"

    license_columns = [
        {"key": "ne_type", "label": "NE тип"},
        {"key": "city", "label": "Город"},
        {"key": "site", "label": "Сайт"},
        {"key": "year", "label": "Год"},
        {"key": "lsn", "label": "LSN"},
        {"key": "product", "label": "Продукт"},
        {"key": "version", "label": "Версия"},
        {"key": "esn", "label": "ESN"},
        {"key": "domain", "label": "Домен"},
        {"key": "license_kind", "label": "Тип лицензии"},
        {"key": "expire_disp", "label": "Срок действия"},
    ]

    lic_metrics = {
        "unique_esn": (
            "Уникальные ESN в БД",
            "Кликните по строке или иконке, чтобы открыть детали лицензии. Отметьте чекбоксы для пакетного просмотра.",
            state["active"],
            list_url,
        ),
        "coverage": (
            "Покрытие ESN-маппинга",
            "Узлы из ESN-маппинга, для которых в БД найдены актуальные лицензии.",
            state["covered_esn_rows"],
            list_url,
        ),
        "unmapped_esn": (
            "Неизвестные ESN (нет в маппинге)",
            "Лицензии есть в БД, но их ESN отсутствуют в ESN-маппинге оператора.",
            state["unmapped_esn_rows"],
            list_url,
        ),
        "permanent": (
            "Только Permanent",
            "Актуальные лицензии с бессрочными ресурсами.",
            state["buckets"]["permanent"],
            list_url,
        ),
        "fixterm": (
            "Только Fixterm",
            "Актуальные лицензии со срочными (временными) ресурсами.",
            state["buckets"]["fixterm"],
            list_url,
        ),
        "permanent_fixterm": (
            "Permanent + Fixterm",
            "Комбинированные лицензии, содержащие одновременно бессрочные и срочные ресурсы.",
            state["buckets"]["permanent_fixterm"],
            list_url,
        ),
        "expired": (
            "Просроченные лицензии (Expired)",
            "Лицензии, у которых дата истечения уже прошла.",
            sorted(state["buckets"]["expired"], key=lambda x: (x["days_left"] if x["days_left"] is not None else 999999)),
            f"/{operator}/expiring",
        ),
        "expiring_30": (
            "Истекают в ближайшие 30 дней",
            "Лицензии со сроком окончания от 0 до 30 дней.",
            sorted(state["buckets"]["expiring_30"], key=lambda x: (x["days_left"] if x["days_left"] is not None else 999999)),
            f"/{operator}/expiring",
        ),
        "expiring_90": (
            "Истекают через 31–90 дней",
            "Лицензии для планового продления (31–90 дней).",
            sorted(state["buckets"]["expiring_90"], key=lambda x: (x["days_left"] if x["days_left"] is not None else 999999)),
            f"/{operator}/expiring",
        ),
    }

    if metric in lic_metrics:
        title, subtitle, items, target_url = lic_metrics[metric]
        return {
            "mode": "licenses",
            "title": title,
            "subtitle": subtitle,
            "columns": license_columns,
            "records": _format_license_records(operator, items),
            "list_url": target_url,
        }

    if metric == "total_licenses":
        all_items = []
        for l in state["all_licenses"]:
            all_items.append({
                "id": l.get("id"),
                "esn": l.get("esn") or "",
                "lsn": l.get("lsn") or "-",
                "ne_type": l.get("ne_type") or "-",
                "city": l.get("city") or "-",
                "site": l.get("site") or "-",
                "year": l.get("year") or "-",
                "domain": l.get("domain") or "-",
                "product": l.get("product") or "-",
                "version": l.get("version") or "-",
                "valid_date": l.get("valid_date") or "-",
                "nearest_expire": l.get("valid_date") or "-",
                "days_left": None,
                "license_kind": l.get("filename") or "-",
            })
        return {
            "mode": "licenses",
            "title": "Все файлы лицензий в БД (с историей)",
            "subtitle": "Все записи лицензий оператора в БД. Клик по строке открывает карточку лицензии.",
            "columns": license_columns,
            "records": _format_license_records(operator, all_items),
            "list_url": list_url,
        }

    if metric == "missing_esn":
        return {
            "mode": "table",
            "title": "ESN без лицензий в БД (Gap)",
            "subtitle": "Записи из ESN-маппинга оператора, для которых в БД пока нет лицензий.",
            "headers": ["ESN", "LSN", "Домен", "Поддомен", "NE тип", "Город", "Сайт"],
            "rows": [
                [r["esn"], r["lsn"], r["domain"], r["sub_domain"], r["ne_type"], r["city"], r["site"]]
                for r in state["missing_esn_rows"]
            ],
            "list_url": "/settings",
        }

    if metric == "ne_types":
        rows = []
        for ne, st in sorted(state["ne_stats"].items(), key=lambda x: (-x[1]["esn_count"], x[0])):
            rows.append([ne, st["esn_count"], st["perm"], st["fix"], st["both"], st["risk"], len(st["cities"])])
        return {
            "mode": "table",
            "title": "Распределение по типам NE",
            "subtitle": "Сводка по уникальным ESN, типам лицензий и рискам по типам оборудования.",
            "headers": ["NE тип", "Уник. ESN", "Permanent", "Fixterm", "Perm+Fix", "Риск ≤30д", "Городов"],
            "rows": rows,
            "list_url": list_url,
        }

    if metric == "cities":
        rows = []
        for city, st in sorted(state["city_stats"].items(), key=lambda x: (-x[1]["esn_count"], x[0])):
            rows.append([city, st["esn_count"], len(st["ne_types"]), len(st["sites"]), st["risk"]])
        return {
            "mode": "table",
            "title": "Распределение по городам",
            "subtitle": "Сводка по уникальным ESN, типам NE, площадкам и рискам по городам.",
            "headers": ["Город", "Уник. ESN", "Типов NE", "Сайтов", "Риск ≤30д"],
            "rows": rows,
            "list_url": list_url,
        }

    if metric == "db_status":
        s = state["summary"]
        return {
            "mode": "table",
            "title": "Статус базы данных и синхронизации",
            "subtitle": "Техническая сводка по локальной БД оператора.",
            "headers": ["Параметр", "Значение"],
            "rows": [
                ["Оператор", op_title or operator],
                ["Всего записей лицензий в БД", s["total_licenses_count"]],
                ["Файлов .DAT", s["dat_count"]],
                ["Файлов .XML", s["xml_count"]],
                ["Уникальных ESN в БД", s["unique_esn_count"]],
                ["ESN в маппинге", s["mapped_esn_count"]],
                ["Последнее обновление БД", s["last_db_update"]],
                ["Ожидают синхронизации (pending)", s["pending_sync"]],
            ],
            "list_url": list_url,
        }

    return {
        "mode": "table",
        "title": "Детализация",
        "subtitle": f"Неизвестная метрика: {metric}",
        "headers": ["Сообщение"],
        "rows": [["Данные не найдены"]],
        "list_url": list_url,
    }
