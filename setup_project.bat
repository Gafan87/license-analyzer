@echo off
chcp 65001 >nul
title Создание структуры проекта Анализатор лицензий
echo ================================================
echo   Создание структуры проекта
echo   Анализатор лицензий Huawei
echo ================================================
echo.

REM === Создание папок ===
echo [1/6] Создание папок...

mkdir license_analyzer 2>nul
cd license_analyzer

mkdir excel_formulas 2>nul
mkdir operators 2>nul
mkdir operators\mts 2>nul
mkdir operators\beeline 2>nul
mkdir logs 2>nul
mkdir modules 2>nul
mkdir modules\web 2>nul
mkdir templates 2>nul
mkdir static 2>nul
mkdir static\css 2>nul
mkdir static\js 2>nul

echo [OK] Папки созданы
echo.

REM === Создание пустых Python файлов в modules ===
echo [2/6] Создание файлов modules...

echo # Модуль логирования > modules\logger.py
echo # Сканер файлов > modules\scanner.py
echo # Парсер XML > modules\parser_xml.py
echo # Парсер DAT > modules\parser_dat.py
echo # Работа с БД > modules\database.py
echo # Вычисление формул из Excel > modules\excel_evaluator.py
echo # Управление целями > modules\target_manager.py
echo # Пустой init > modules\__init__.py

echo # Веб маршруты > modules\web\routes.py
echo # Пустой init > modules\web\__init__.py

echo [OK] Файлы modules созданы
echo.

REM === Создание HTML шаблонов ===
echo [3/6] Создание HTML шаблонов...

echo {%% extends "base.html" %%} > templates\index.html
echo {%% extends "base.html" %%} > templates\reports.html
echo {%% extends "base.html" %%} > templates\export.html
echo {%% extends "base.html" %%} > templates\settings.html
echo {%% extends "base.html" %%} > templates\base_targets.html
echo {%% extends "base.html" %%} > templates\license_detail.html
echo ^<!DOCTYPE html^> > templates\base.html

echo [OK] HTML шаблоны созданы
echo.

REM === Создание конфигурационных файлов ===
echo [4/6] Создание конфигурационных файлов...

echo { > config.json
echo   "log_level": "INFO", >> config.json
echo   "operators": [ >> config.json
echo     { >> config.json
echo       "name": "mts", >> config.json
echo       "title": "МТС", >> config.json
echo       "storage_path": "D:/LicenseStorage/MTS", >> config.json
echo       "folder_structure": [ >> config.json
echo         {"level": 1, "name": "ne_type"}, >> config.json
echo         {"level": 2, "name": "city"}, >> config.json
echo         {"level": 3, "name": "year"} >> config.json
echo       ] >> config.json
echo     }, >> config.json
echo     { >> config.json
echo       "name": "beeline", >> config.json
echo       "title": "Beeline", >> config.json
echo       "storage_path": "D:/LicenseStorage/Beeline", >> config.json
echo       "folder_structure": [ >> config.json
echo         {"level": 1, "name": "ne_type"}, >> config.json
echo         {"level": 2, "name": "city"}, >> config.json
echo         {"level": 3, "name": "year"} >> config.json
echo       ] >> config.json
echo     } >> config.json
echo   ] >> config.json
echo } >> config.json

echo # Главный файл приложения > app.py
echo # Файл с зависимостями > requirements.txt

echo [OK] Конфигурационные файлы созданы
echo.

REM === Создание примеров Excel файлов ===
echo [5/6] Создание примеров Excel файлов...

echo Создайте вручную файлы в папке excel_formulas/:
echo   - vEPC_formulas.xlsx
echo   - PSCORE_formulas.xlsx
echo   - PCRF_formulas.xlsx
echo.
echo Пример структуры Excel:
echo   | CapacityKey | Формула | Коэф_МТС | Коэф_Билайн |
echo   | LKV2UPTR01  | =30000  | 1.0      | 1.0       |
echo   | LKV2WSUBS01 | =B2*C2  | 1.5      | 2.0       |

echo [OK] Примеры описаны
echo.

REM === Создание README ===
echo [6/6] Создание README...

echo # Анализатор лицензий Huawei > README.md
echo. >> README.md
echo ## Установка >> README.md
echo 1. Установите Python 3.10+ >> README.md
echo 2. Запустите `pip install -r requirements.txt` >> README.md
echo 3. Отредактируйте `config.json` (укажите пути к лицензиям) >> README.md
echo 4. Запустите `python app.py` >> README.md
echo. >> README.md
echo ## Структура >> README.md
echo - `operators/` - данные по операторам >> README.md
echo - `excel_formulas/` - Excel файлы с формулами >> README.md
echo - `logs/` - логи программы >> README.md
echo - `templates/` - HTML шаблоны >> README.md

echo [OK] README создан
echo.

REM === Установка зависимостей ===
echo [Дополнительно] Установка Python пакетов...
echo.
echo Запустите вручную после установки Python:
echo   pip install flask openpyxl
echo.

REM === Итог ===
echo ================================================
echo   ГОТОВО!
echo ================================================
echo.
echo Структура проекта создана в папке: %cd%
echo.
echo Что делать дальше:
echo 1. Установите Python с python.org
echo 2. Откройте командную строку в папке license_analyzer
echo 3. Выполните: pip install flask openpyxl
echo 4. Отредактируйте config.json (путь к лицензиям)
echo 5. Скопируйте код из приложения в соответствующие файлы
echo 6. Запустите: python app.py
echo.
echo Для быстрого запуска создайте файл start.bat:
echo   @echo off
echo   cd /d "%~dp0"
echo   python app.py
echo   pause
echo.
pause