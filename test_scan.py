# test_scan_debug.py
import sys
sys.path.insert(0, 'D:\\MyDocs\\License management')

from flask import Flask
app = Flask(__name__)

with app.app_context():
    from modules.scanner import scan_local_folder
    path = r'D:\_Beeline\_Licenses\_All Licenses\PS_CORE\CG9812\2027-03-01'
    result = scan_local_folder(path, 'veon')
    
    print(f'Найдено: {len(result)}')
    if result:
        print(f'Первый файл: {result[0].get("filename")}')
        print(f'Ресурсов: {len(result[0].get("resources", []))}')
        if result[0].get('resources'):
            print('Первый ресурс:', result[0]['resources'][0])