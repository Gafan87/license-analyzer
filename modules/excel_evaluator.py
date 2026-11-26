import openpyxl
import os
import re
from modules.logger import get_logger

logger = get_logger(__name__)

class ExcelFormulaEvaluator:
    """Вычисляет цели по формулам из Excel"""
    
    def __init__(self, ne_type):
        self.ne_type = ne_type
        self.excel_path = f"excel_formulas/{ne_type}_formulas.xlsx"
        self.formulas = {}
        self.dependencies = {}
        
    def load(self):
        """Загружает Excel файл с формулами"""
        if not os.path.exists(self.excel_path):
            logger.warning(f"Excel файл не найден: {self.excel_path}")
            return False
        
        wb = openpyxl.load_workbook(self.excel_path, data_only=False)
        sheet = wb.active
        
        # Читаем заголовки
        headers = [cell.value for cell in sheet[1]]
        
        # Находим колонки
        formula_col = None
        coeff_cols = {}
        
        for idx, h in enumerate(headers, 1):
            if h and 'формул' in str(h).lower():
                formula_col = idx
            elif h and 'коэф' in str(h).lower():
                coeff_cols[h] = idx
        
        if not formula_col:
            formula_col = 2
        
        # Читаем формулы
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            
            cap_key = row[0]
            formula = row[formula_col - 1] if formula_col <= len(row) else None
            
            if formula:
                self.formulas[cap_key] = str(formula)
                # Ищем зависимости {KEY}
                deps = re.findall(r'\{([A-Z0-9_]+)\}', str(formula))
                self.dependencies[cap_key] = deps
        
        logger.info(f"Загружено {len(self.formulas)} формул для {self.ne_type}")
        return True
    
    def calculate(self, base_values, coeffs=None):
        """Вычисляет цели на основе базовых значений и коэффициентов"""
        if not self.formulas and not self.load():
            return base_values
        
        results = base_values.copy()
        calculated = set(base_values.keys())
        
        # Максимум 100 итераций
        for _ in range(100):
            progress = False
            for cap_key, formula in self.formulas.items():
                if cap_key in calculated:
                    continue
                
                deps = self.dependencies.get(cap_key, [])
                if all(dep in calculated for dep in deps):
                    try:
                        expr = str(formula)
                        # Подставляем значения зависимостей
                        for dep in deps:
                            expr = expr.replace(f'{{{dep}}}', str(results.get(dep, 0)))
                        # Подставляем коэффициенты
                        if coeffs:
                            for coeff_name, coeff_value in coeffs.items():
                                expr = expr.replace(f'{{{coeff_name}}}', str(coeff_value))
                        # Безопасное вычисление
                        result = eval(expr)
                        results[cap_key] = int(result) if isinstance(result, (int, float)) else 0
                        calculated.add(cap_key)
                        progress = True
                    except Exception as e:
                        logger.error(f"Ошибка вычисления {cap_key}: {formula} -> {e}")
            
            if not progress:
                break
        
        return results