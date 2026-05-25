import re
import pandas as pd
from collections import defaultdict
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os

def parse_license_file(filename):
    # Храним: код -> [описание, auth, real, usage, left, ntimes]
    license_data = defaultdict(lambda: ['', 0, 0, 0, 0, 0])

    pattern = re.compile(
        r'^\s*(?P<code>\w+)\s+'
        r'(?P<desc>.+?)\s{2,}'        # Описание — всё до двух и более пробелов
        r'\w+\s+'                      # Тип (Resource и т.п.)
        r'(?P<auth>\d+)\s+'
        r'(?P<real>\d+)\s+'
        r'(?P<usage>\d+)\s+'
        r'(?P<left>\d+)\s+'
        r'(?P<ntimes>\d+)'
    )

    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                code = match.group('code')
                desc = match.group('desc').strip()
                license_data[code][0] = desc  # описание
                license_data[code][1] += int(match.group('auth'))
                license_data[code][2] += int(match.group('real'))
                license_data[code][3] += int(match.group('usage'))
                license_data[code][4] += int(match.group('left'))
                license_data[code][5] += int(match.group('ntimes'))

    if not license_data:
        return None

    rows = []
    for code, (desc, auth, real, usage, left, ntimes) in license_data.items():
        rows.append([code, desc, auth, real, usage, left, ntimes])

    df = pd.DataFrame(rows, columns=['License ID', 'License Item', 'Authorization-values',
                                      'Real-values', 'Usage-percent(%)', 'Left-percent(%)', 'N-TIMES'])
    return df

class LicenseParserApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Парсер лицензий DAT → Excel")
        self.root.geometry("550x320")
        self.root.resizable(False, False)
        
        title = tk.Label(root, text="Парсер файла лицензий", 
                        font=("Arial", 14, "bold"), pady=10)
        title.pack()
        
        file_frame = tk.Frame(root)
        file_frame.pack(pady=15, padx=20, fill=tk.X)
        
        tk.Label(file_frame, text="DAT файл:", font=("Arial", 10)).pack(side=tk.LEFT)
        
        self.file_path = tk.StringVar()
        self.file_entry = tk.Entry(file_frame, textvariable=self.file_path, 
                                   width=45, font=("Arial", 9))
        self.file_entry.pack(side=tk.LEFT, padx=5)
        
        browse_btn = tk.Button(file_frame, text="Обзор...", command=self.browse_file,
                              bg="#e0e0e0", font=("Arial", 9))
        browse_btn.pack(side=tk.LEFT)
        
        hint = tk.Label(root, text="Можно перетащить файл в поле выше или нажать Обзор", 
                       font=("Arial", 8), fg="gray")
        hint.pack(pady=(0, 10))
        
        self.progress = ttk.Progressbar(root, mode='indeterminate', length=400)
        
        self.run_btn = tk.Button(root, text="▶ Обработать и сохранить в Excel", 
                                command=self.process_file,
                                bg="#4CAF50", fg="white", 
                                font=("Arial", 11, "bold"),
                                padx=20, pady=8,
                                cursor="hand2")
        self.run_btn.pack(pady=15)
        
        self.status = tk.Label(root, text="Ожидание файла...", 
                              font=("Arial", 9), fg="gray")
        self.status.pack(pady=5)
    
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите DAT файл",
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        if filename:
            self.file_path.set(filename)
    
    def process_file(self):
        input_file = self.file_path.get().strip()
        
        if not input_file:
            messagebox.showwarning("Внимание", "Сначала выберите DAT файл!")
            return
        
        if not os.path.exists(input_file):
            messagebox.showerror("Ошибка", f"Файл не найден:\n{input_file}")
            return
        
        output_file = os.path.splitext(input_file)[0] + "_summary.xlsx"
        
        self.run_btn.config(state=tk.DISABLED, text="Обработка...")
        self.progress.pack(pady=5)
        self.progress.start()
        self.status.config(text="Обработка...", fg="orange")
        self.root.update()
        
        try:
            result_df = parse_license_file(input_file)
            
            if result_df is None:
                messagebox.showwarning("Результат", 
                    "В файле не найдено строк с данными лицензий.\nПроверьте формат файла.")
                self.status.config(text="Данные не найдены", fg="red")
            else:
                result_df.to_excel(output_file, index=False, sheet_name='Summary')
                messagebox.showinfo("Готово!", 
                    f"Обработано успешно!\n\n"
                    f"Найдено уникальных кодов: {len(result_df)}\n"
                    f"Файл сохранен:\n{output_file}")
                self.status.config(text=f"Готово! {len(result_df)} кодов -> {output_file}", fg="green")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать файл:\n{str(e)}")
            self.status.config(text="Ошибка обработки", fg="red")
        finally:
            self.progress.stop()
            self.progress.pack_forget()
            self.run_btn.config(state=tk.NORMAL, text="▶ Обработать и сохранить в Excel")

if __name__ == "__main__":
    root = tk.Tk()
    app = LicenseParserApp(root)
    root.mainloop()
