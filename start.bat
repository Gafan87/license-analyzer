@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   ЗАПУСК АНАЛИЗАТОРА ЛИЦЕНЗИЙ HUAWEI
echo ========================================
echo.
echo Текущая папка: %cd%
echo.

:: Проверяем наличие app.py
if not exist "app.py" (
    echo [ОШИБКА] app.py не найден в %cd%
    echo.
    echo Убедитесь, что start.bat находится в папке с программой
    pause
    exit /b 1
)
echo [OK] app.py найден
echo.

:: Проверяем наличие config.json
if not exist "config.json" (
    echo [ОШИБКА] config.json не найден
    echo Запустите setup_project.bat сначала
    pause
    exit /b 1
)
echo [OK] config.json найден
echo.

:: Проверяем наличие папок
if not exist "modules" (
    echo [ОШИБКА] Папка modules не найдена
    pause
    exit /b 1
)
echo [OK] Структура папок проверена
echo.

:: Пробуем разные способы запуска Python
echo Поиск Python...

:: Способ 1: через py (Python Launcher)
py -c "print('OK')" > nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Найден: py (Python Launcher)
    set PYTHON_CMD=py
    goto :run
)

:: Способ 2: через python
python -c "print('OK')" > nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Найден: python
    set PYTHON_CMD=python
    goto :run
)

:: Способ 3: полный путь Python 3.13
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe" (
    echo [OK] Найден: Python 3.13
    set PYTHON_CMD="C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"
    goto :run
)

:: Способ 4: полный путь Python 3.12
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
    echo [OK] Найден: Python 3.12
    set PYTHON_CMD="C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
    goto :run
)

:: Способ 5: полный путь Python 3.11
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    echo [OK] Найден: Python 3.11
    set PYTHON_CMD="C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    goto :run
)

:: Способ 6: полный путь Python 3.10
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe" (
    echo [OK] Найден: Python 3.10
    set PYTHON_CMD="C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
    goto :run
)

:: Способ 7: через where (последняя попытка)
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo [OK] Найден: %%i
    set PYTHON_CMD="%%i"
    goto :run
)

:: Если ничего не нашли
echo.
echo [ОШИБКА] Python не найден!
echo.
echo Установите Python с официального сайта:
echo https://www.python.org/downloads/
echo.
echo ВАЖНО: При установке поставьте галочку "Add Python to PATH"
echo.
pause
exit /b 1

:run
echo.
echo ========================================
echo   ЗАПУСК СЕРВЕРА
echo ========================================
echo.
echo Команда: %PYTHON_CMD% app.py
echo.
echo Адрес: http://127.0.0.1:5000
echo.
echo Для остановки нажмите Ctrl+C
echo ========================================
echo.

:: Открываем браузер с задержкой
timeout /t 2 /nobreak > nul
start http://127.0.0.1:5000

:: Запускаем сервер
%PYTHON_CMD% app.py

:: Сюда попадаем после остановки сервера
echo.
echo ========================================
echo   СЕРВЕР ОСТАНОВЛЕН
echo ========================================
echo.
pause