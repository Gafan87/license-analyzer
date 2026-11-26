import os
os.chdir(r"D:\MyDocs\License management")

p = "patch.py"
with open(p, "r", encoding="utf-8") as f:
    txt = f.read()

lines = txt.splitlines(keepends=True)
out = []
for line in lines:
    if line.startswith("                SELECT operator, domain, ne_type, version, city, city_full, site,") or \
       line.startswith("                       year, valid_date, lsn, esn, create_time") or \
       line.startswith("                FROM licenses") or \
       line.startswith("                WHERE domain IS NOT NULL AND TRIM(domain) != ''"):
        out.append(line[4:])
    else:
        out.append(line)

new_txt = "".join(out)
with open(p, "w", encoding="utf-8") as f:
    f.write(new_txt)
print("FIXED patch.py")