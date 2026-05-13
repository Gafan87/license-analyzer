import xml.etree.ElementTree as ET

file_path = r'D:\_Beeline\_Licenses\_All Licenses\vEPC_CORE\NSK\2028-03-01\LICUDG_NSK_vEPC1_2027.xml'

try:
    tree = ET.parse(file_path)
    root = tree.getroot()
    
    print('Корневой тег:', root.tag)
    print()
    
    # Ищем SalesItem
    sales_items = root.findall('.//SalesItem')
    print('Найдено SalesItem:', len(sales_items))
    
    if sales_items:
        for si in sales_items[:3]:
            print('  - name:', si.get('name'), 'value:', si.get('value'))
    
    print()
    
    # Ищем CapacityKey
    capacity_keys = root.findall('.//CapacityKey')
    print('Найдено CapacityKey:', len(capacity_keys))
    if capacity_keys:
        for ck in capacity_keys[:5]:
            print('  - name:', ck.get('name'), 'value:', ck.get('value'))
    
    print()
    
    # Все уникальные теги
    all_tags = set()
    for elem in root.iter():
        all_tags.add(elem.tag)
    print('Все теги в файле:', sorted(all_tags))
    
except Exception as e:
    print(f'Ошибка: {e}')