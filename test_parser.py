# test_parser.py
import sys
sys.path.insert(0, 'D:\\MyDocs\\License management')
from modules.parser_dat import parse_dat_license

result = parse_dat_license(r'D:\_Beeline\_Licenses\_All Licenses\CS_CORE\LICMSX-ATCA_Ekaterinburg4_2024.dat')
if result:
    print(f"LSN: {result.get('lsn')}")
    print(f"Ресурсов: {len(result.get('resources', []))}")
    for r in result.get('resources', [])[:5]:
        print(f"  {r}")
else:
    print("Ошибка парсинга")