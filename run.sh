#!/usr/bin/env bash
# run.sh - Скрипт быстрого запуска для Linux / macOS / Git Bash

set -e

echo "[1/3] Установка зависимостей Python..."
pip install -r requirements.txt

echo "[2/3] Установка Chromium для Playwright..."
playwright install chromium

echo "[3/3] Запуск скрапера..."
python scraper.py "$@"
