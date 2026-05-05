from modules.database import get_base_targets, save_base_target
from modules.logger import get_logger

logger = get_logger(__name__)

def get_targets_for_site(operator, ne_type, city, site):
    """Получает все цели для конкретного сайта"""
    return get_base_targets(operator, ne_type, city, site)

def save_target_for_site(operator, ne_type, city, site, capacity_key, target_value, updated_by):
    """Сохраняет цель для сайта"""
    save_base_target(operator, ne_type, city, site, capacity_key, target_value, updated_by)
    logger.info(f"Сохранена цель {capacity_key}={target_value} для {operator}/{ne_type}/{city}/{site}")

def get_actual_resources_for_site(operator, ne_type, city, site, year):
    """Получает фактические ресурсы для сайта за указанный год"""
    from modules.database import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.capacity_key, r.value
        FROM resources r
        JOIN licenses l ON r.license_id = l.id
        WHERE l.operator = ? AND l.ne_type = ? AND l.city = ? AND l.site = ? AND l.year = ?
    ''', (operator, ne_type, city, site, year))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {r[0]: r[1] for r in rows}

def compare_with_targets(operator, ne_type, city, site, year):
    """Сравнивает фактические ресурсы с целями"""
    targets = get_targets_for_site(operator, ne_type, city, site)
    actual = get_actual_resources_for_site(operator, ne_type, city, site, year)
    
    comparison = []
    for cap_key, target_val in targets.items():
        actual_val = actual.get(cap_key, 0)
        deviation = 0
        if target_val > 0:
            deviation = round((actual_val - target_val) / target_val * 100, 1)
        
        comparison.append({
            'capacity_key': cap_key,
            'target_value': target_val,
            'actual_value': actual_val,
            'deviation': deviation,
            'status': 'danger' if deviation < 0 else 'success' if deviation >= 0 else 'warning'
        })
    
    return comparison