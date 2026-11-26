import os, re
os.chdir(r"D:\MyDocs\License management")

print("=== 1. routes.py: render_template in excel_mapping ===")
with open("modules/web/routes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

tpl_name = None
for i in range(2826, min(len(lines), 3150)):
    line = lines[i]
    if "render_template(" in line:
        for j in range(max(2826, i - 2), min(len(lines), i + 12)):
            print(f"{j+1:4d}: {lines[j].rstrip()}")
        m = re.search(r"render_template\(\s*['\"]([^'\"]+)['\"]", line)
        if m:
            tpl_name = m.group(1)
        break

print("\n=== 2. base.html: settings endpoint checks ===")
with open("templates/base.html", "r", encoding="utf-8") as f:
    b_lines = f.readlines()
for idx, line in enumerate(b_lines, 1):
    if "web.settings" in line or "action-cards" in line:
        for j in range(max(1, idx - 2), min(len(b_lines), idx + 4) + 1):
            print(f"{j:4d}: {b_lines[j-1].rstrip()}")
        print("---")

if tpl_name:
    tpl_path = os.path.join("templates", tpl_name)
    print(f"\n=== 3. {tpl_path} (top 25 lines) ===")
    if os.path.exists(tpl_path):
        with open(tpl_path, "r", encoding="utf-8") as f:
            t_lines = f.readlines()
        for idx in range(1, min(len(t_lines), 25) + 1):
            print(f"{idx:4d}: {t_lines[idx-1].rstrip()}")