import requests

resp = requests.get('http://127.0.0.1:5000/api/license/3764/hierarchy?domain=IMS&mode=total')
data = resp.json()

spart = next((s for s in data['sparts'] if s['name'] == 'KVCS036AUU00'), None)
print('SPart KVCS036AUU00:')
print('  value:', spart['value'])
print('  children count:', len(spart['children']))
print('  первые 5 children:')
for c in spart['children'][:5]:
    print('    -', c['name'], c['value'])