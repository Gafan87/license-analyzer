# test_scan.py
import sys
sys.path.insert(0, r'D:\MyDocs\License management')

from modules.scanner import scan_local_folder

path = r'D:\_Beeline\_Licenses\_All Licenses\CS_CORE'
result = scan_local_folder(path, 'veon')

print(f'Найдено лицензий: {len(result)}')
for i, lic in enumerate(result[:3]):
    print(f'{i}: {lic.get("filename")} - LSN: {lic.get("lsn")} - Ресурсов: {len(lic.get("resources", []))}')