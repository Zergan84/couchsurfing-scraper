"""
auth.py - Скрипт первоначальной авторизации в Couchsurfing.

Открывает окно браузера (Google Chrome или встроенный Chromium) для ручного входа
и сохраняет состояние сессии (cookies и local storage) в:
- user_data/auth_state.json (для моментального экспорта/импорта сессии)
- user_data/ (persistent profile)
"""

import os
import sys
import time
from pathlib import Path

# Установка кодировки UTF-8 для вывода на Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
AUTH_STATE_FILE = USER_DATA_DIR / "auth_state.json"
SIGN_IN_URL = "https://www.couchsurfing.com/users/sign_in"


def run_auth():
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[*] Инициализация авторизации...")
    print(f"[*] Директория профиля: {USER_DATA_DIR.resolve()}")
    print("[*] Запуск браузера...")

    with sync_playwright() as p:
        # Пробуем использовать установленный в системе Google Chrome, либо chromium
        browser = None
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--start-maximized",
        ]
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=False,
                args=launch_args,
            )
            print("[+] Запущен браузер Google Chrome")
        except Exception:
            browser = p.chromium.launch(
                headless=False,
                args=launch_args,
            )
            print("[+] Запущен Playwright Chromium")

        # Создаем контекст с эмуляцией обычного окна
        context_kwargs = {
            "no_viewport": True,
            "user_agent": user_agent,
        }
        if AUTH_STATE_FILE.exists():
            context_kwargs["storage_state"] = str(AUTH_STATE_FILE)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        print(f"[*] Открытие страницы: {SIGN_IN_URL}")
        try:
            page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[!] Примечание при загрузке: {e}")

        print("\n" + "=" * 60)
        print("ИНСТРУКЦИЯ:")
        print("1. В открывшемся окне браузера войдите в свой аккаунт Couchsurfing.")
        print("2. Пройдите проверку Cloudflare/капчу (если есть).")
        print("3. Как только вы войдете в личный кабинет (dashboard/лента),")
        print("   скрипт автоматически зафиксирует вход и сохранит auth_state.json!")
        print("=" * 60 + "\n")

        # Мониторим статус авторизации
        start_time = time.time()
        saved = False

        while time.time() - start_time < 360:  # до 6 минут на авторизацию
            try:
                curr_url = page.url.lower()

                # Проверка наличия cookies couchsurfing
                cookies = context.cookies()
                has_session = any(
                    "session" in c["name"].lower() or "couchsurfing" in c["domain"].lower()
                    for c in cookies
                )

                # Если пользователь перешел на любую страницу внутри Couchsurfing (не логин)
                if has_session and ("/dashboard" in curr_url or "/members" in curr_url or "/feed" in curr_url or "/home" in curr_url or "/people/" in curr_url):
                    print(f"\n[+] Авторизация подтверждена на URL: {page.url}")
                    context.storage_state(path=str(AUTH_STATE_FILE))
                    print(f"[+] Сессия успешно сохранена в {AUTH_STATE_FILE.resolve()}")
                    saved = True
                    time.sleep(2)
                    break
            except Exception:
                # Окно могло быть закрыто пользователем
                break

            time.sleep(2)

        if not saved:
            # Сохраняем текущее состояние перед закрытием на случай, если пользователь уже авторизовался
            try:
                context.storage_state(path=str(AUTH_STATE_FILE))
                print(f"[*] Состояние сессии сохранено: {AUTH_STATE_FILE.resolve()}")
            except Exception:
                pass

        try:
            context.close()
            browser.close()
        except Exception:
            pass

        print("[+] Готово! Теперь можно переходить к сбору анкет.")


if __name__ == "__main__":
    run_auth()
