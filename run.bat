@echo off
REM run.bat - Скрипт быстрого запуска для Windows

echo [1/3] Установка зависимостей Python...
pip install -r requirements.txt
if errorlevel 1 goto error

echo [2/3] Установка Chromium для Playwright...
playwright install chromium
if errorlevel 1 goto error

echo [3/3] Запуск скрапера...
python scraper.py %*
goto end

:error
echo Произошла ошибка при выполнении.
exit /b 1

:end
