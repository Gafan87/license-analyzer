import openpyxl

FILE = r"\\A00742028-C5NC5\_Licenses\mapping\targets.xlsx"

wb = openpyxl.load_workbook(FILE, data_only=True)

print("=== ЛИСТЫ ===")
for name in wb.sheetnames:
    print(f"  '{name}'  (len={len(name)})")

print("\n=== ЗАГОЛОВКИ КАЖДОГО ЛИСТА ===")
for name in wb.sheetnames:
    sheet = wb[name]
    headers = [c.value for c in next(sheet.iter_rows(min_row=1, max_row=1))]
    print(f"\n  [{name}] headers:")
    for i, h in enumerate(headers):
        print(f"    {i}: {repr(h)}")

print("\n=== ПЕРВЫЕ 5 СТРОК TARGETS ===")
if 'Targets' in wb.sheetnames:
    sheet = wb['Targets']
    for i, row in enumerate(sheet.iter_rows(min_row=1, max_row=6, values_only=True), 1):
        print(f"  Row {i}: {row}")

print("\n=== ПЕРВЫЕ 5 СТРОК FORMULAS ===")
for candidate in ['Formulas', 'formulas', 'Formula', ' Form']:
    if candidate in wb.sheetnames:
        sheet = wb[candidate]
        for i, row in enumerate(sheet.iter_rows(min_row=1, max_row=6, values_only=True), 1):
            print(f"  Row {i}: {row}")
        break
else:
    print("  ❌ Лист Formulas не найден среди стандартных имён")

print("\n=== ПЕРВЫЕ 5 СТРОК SHARING ===")
for candidate in ['Sharing', 'sharing', 'Share']:
    if candidate in wb.sheetnames:
        sheet = wb[candidate]
        for i, row in enumerate(sheet.iter_rows(min_row=1, max_row=6, values_only=True), 1):
            print(f"  Row {i}: {row}")
        break
else:
    print("  ❌ Лист Sharing не найден среди стандартных имён")