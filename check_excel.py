import openpyxl

wb = openpyxl.load_workbook('//A00742028-C5NC5/_Licenses/license_details/IMS_license_details.xlsx')
sheet = wb.active

print('Заголовки (первая строка):')
for idx, cell in enumerate(sheet[1], 1):
    print(f'  Колонка {chr(64+idx)}: {cell.value}')

print('\nПервые 3 строки данных:')
for row in list(sheet.iter_rows(min_row=2, values_only=True))[:3]:
    print(row)