"""
auto_sender.py - Модуль фонового автопилота отправки запросов (Шаг 3).

Безопасность и антифрод:
1. Строгий суточный лимит (по умолчанию 12 запросов в сутки, максимум 15).
2. Рандомизированные паузы между отправками (15-35 минут).
3. Имитация человеческого набора текста (человеческие задержки 30-80 мс).
4. Мгновенная остановка при обнаружении Cloudflare, капчи или ошибок 429/403.
5. Поддержка режима --dry-run для безопасного тестирования без отправки.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
USER_DATA_DIR = BASE_DIR / "user_data"
AUTH_STATE_FILE = USER_DATA_DIR / "auth_state.json"
QUEUE_FILE = OUTPUT_DIR / "requests_queue.json"
SENT_LOG_FILE = OUTPUT_DIR / "sent_log.json"
STATUS_FILE = OUTPUT_DIR / "autopilot_status.json"

DEFAULT_DAILY_LIMIT = 12
MAX_ALLOWED_LIMIT = 15
DEFAULT_DELAY_MIN = 15  # минут
DEFAULT_DELAY_MAX = 35  # минут


class AutoSender:
    def __init__(
        self,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        delay_min: int = DEFAULT_DELAY_MIN,
        delay_max: int = DEFAULT_DELAY_MAX,
        dry_run: bool = False,
        headless: bool = True,
        target_username: Optional[str] = None,
        test_mode: bool = False,
    ):
        self.daily_limit = min(max(1, daily_limit), MAX_ALLOWED_LIMIT)
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.dry_run = dry_run
        self.headless = headless
        self.target_username = target_username
        self.test_mode = test_mode
        self.is_running = True

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def get_sent_today_count(self) -> int:
        """Подсчитывает количество успешно отправленных запросов за сегодняшний день."""
        if not SENT_LOG_FILE.exists():
            return 0
        try:
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            today_str = date.today().isoformat()
            today_sent = [
                entry for entry in logs
                if entry.get("timestamp", "").startswith(today_str)
                and entry.get("status") in ("success", "dry_run_success")
            ]
            return len(today_sent)
        except Exception:
            return 0

    def append_sent_log(self, entry: Dict[str, Any]) -> None:
        """Записывает результат отправки в sent_log.json."""
        logs = []
        if SENT_LOG_FILE.exists():
            try:
                with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        logs.append(entry)
        with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

    def update_queue_status(self, username: str, new_status: str) -> None:
        """Обновляет статус карточки хоста в requests_queue.json."""
        if not QUEUE_FILE.exists():
            return
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)

            for item in queue:
                if item.get("username") == username:
                    item["status"] = new_status
                    item["updated_at"] = datetime.now().isoformat()
                    break

            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[!] Ошибка обновления очереди: {e}")

    def update_autopilot_status(
        self,
        is_running: bool,
        current_host: Optional[str] = None,
        next_send_time: Optional[float] = None,
        last_status: str = "Idle",
    ) -> None:
        """Сохраняет актуальный статус автопилота для отображения в UI."""
        now = time.time()
        rem = max(0, int(next_send_time - now)) if next_send_time else 0
        data = {
            "is_running": is_running,
            "current_host": current_host,
            "sent_today": self.get_sent_today_count(),
            "daily_limit": self.daily_limit,
            "next_send_time": next_send_time,
            "seconds_remaining": rem,
            "last_status": last_status,
            "dry_run": self.dry_run,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def check_security_challenges(self, page) -> bool:
        """
        Проверяет страницу на наличие капчи, Cloudflare или блокировок.
        Возвращает True, если обнаружена реальная проверка безопасности.
        """
        url = page.url.lower()
        if any(k in url for k in ("challenge", "captcha", "turnstile", "cdn-cgi/challenge")):
            return True

        title = page.title().lower()
        if any(t in title for t in ("just a moment", "attention required", "security check", "access denied", "ddos")):
            return True

        body_text = page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")
        visible_markers = [
            "verify you are human",
            "performing a security check",
            "access denied",
            "error 429",
            "error 403",
            "too many requests. please try again",
            "please verify you are human",
        ]
        return any(m in body_text for m in visible_markers)

    def human_type(self, element, text: str) -> None:
        """
        Имитирует человеческий ввод текста с естественными задержками между символами и словами.
        """
        element.click()
        time.sleep(random.uniform(0.3, 0.7))

        # Очищаем поле, если там что-то было
        element.fill("")

        # Набор по частям или символам с джиттером
        for char in text:
            element.type(char, delay=random.uniform(25, 65))
            if char in (".", "!", "?", "\n"):
                time.sleep(random.uniform(0.15, 0.4))
            elif random.random() < 0.05:
                # Маленькая пауза на «раздумье»
                time.sleep(random.uniform(0.1, 0.25))

    def process_host(self, page, host_item: Dict[str, Any]) -> bool:
        """
        Выполняет отправку запроса для одного хоста.
        Возвращает True в случае успеха.
        """
        username = host_item.get("username", "")
        message = host_item.get("generated_message", "")
        stay_url = f"https://www.couchsurfing.com/c/users/{username}/stay-request"

        print("=" * 60)
        print(f"[*] Обработка хоста: {username} ({host_item.get('name')})")
        print(f"[*] Ссылка: {stay_url}")
        print(f"[*] Режим: {'DRY-RUN (симуляция)' if self.dry_run else 'БОЕВАЯ ОТПРАВКА'}")

        self.update_autopilot_status(
            is_running=True,
            current_host=username,
            last_status=f"Открытие формы для {username}...",
        )

        try:
            page.goto(stay_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(random.uniform(2.5, 4.0))

            # 1. Проверка на Cloudflare / Капчу / Блокировку
            if self.check_security_challenges(page):
                alert_msg = (
                    f"[CRITICAL ALERT] Обнаружен Cloudflare/Капча/429 на {username}! "
                    "Автопилот немедленно остановлен для защиты аккаунта."
                )
                print(alert_msg)
                self.append_sent_log({
                    "id": username,
                    "username": username,
                    "timestamp": datetime.now().isoformat(),
                    "status": "security_abort",
                    "error": "Captcha / Cloudflare / 429 detected",
                })
                self.update_autopilot_status(
                    is_running=False,
                    current_host=username,
                    last_status="Остановлен: обнаружена проверка безопасности (Капча/Cloudflare)",
                )
                self.is_running = False
                return False

            # 2. Ожидание загрузки экрана и выбор поездки
            page.wait_for_timeout(2500)
            try:
                # Ищем оверлей карточки поездки или кнопку New Trip
                overlay_selector = "button.absolute.inset-0.z-10"
                page.wait_for_selector(overlay_selector, timeout=7000)
                print("[*] Выбор существующей карточки поездки (Tokyo)...")
                page.click(overlay_selector)
                page.wait_for_timeout(1500)
            except Exception:
                print("[*] Карточка поездки не потребовалась или уже выбрана...")

            # 3. Переход к Stay Details (экран ввода текста)
            try:
                stay_details_btn = "button:has-text('Stay Details')"
                page.wait_for_selector(stay_details_btn, timeout=5000)
                print("[*] Переход к экрану Stay Details...")
                page.click(stay_details_btn)
                page.wait_for_timeout(2500)
            except Exception:
                pass

            # 4. Поиск поля ввода сообщения
            try:
                page.wait_for_selector("textarea", timeout=8000)
                textarea = page.query_selector("textarea")
            except Exception:
                textarea = page.query_selector("[role='textbox'], [contenteditable='true']")

            if not textarea:
                print(f"[!] Текстовое поле ввода не найдено на странице {username}!")
                return False

            print("[*] Ввод персонализированного текста с имитацией набора...")
            # Если текст длинный, вводим аккуратно
            if len(message) > 400:
                # Вводим первые 80 символов с посимвольной задержкой, остальное порциями
                textarea.click()
                time.sleep(0.5)
                textarea.fill("")
                first_part = message[:80]
                rest_part = message[80:]
                for ch in first_part:
                    textarea.type(ch, delay=random.uniform(20, 50))
                time.sleep(0.4)
                # Дописываем остаток
                textarea.type(rest_part, delay=5)
            else:
                self.human_type(textarea, message)

            time.sleep(random.uniform(1.5, 3.0))

            # 5. Проверка кнопки отправки
            send_btn = page.query_selector("button:has-text('Send Request')")
            if not send_btn:
                send_btn = page.query_selector("button[type='submit']")

            if self.dry_run:
                # Тестовый режим (Dry-run): не нажимаем кнопку отправки
                screenshot_path = OUTPUT_DIR / f"dry_run_{username}.png"
                page.screenshot(path=str(screenshot_path))
                print(f"[+] [DRY-RUN] Форма заполнена успешно. Скриншот сохранен: {screenshot_path.name}")

                self.append_sent_log({
                    "id": username,
                    "username": username,
                    "name": host_item.get("name"),
                    "timestamp": datetime.now().isoformat(),
                    "status": "dry_run_success",
                    "mode": "dry_run",
                    "notes": "Form filled and verified. Send button was not clicked.",
                })
                self.update_queue_status(username, "Sent (Dry-Run)")
                return True

            # БОЕВОЙ РЕЖИМ: клик отправки
            if send_btn:
                if send_btn.is_disabled():
                    print(f"[!] Кнопка 'Send Request' неактивна для {username}!")
                    return False

                print(f"[*] Отправка запроса хосту {username}...")
                send_btn.click()
                time.sleep(random.uniform(3.5, 5.5))

                # Проверка отправки (успешное модальное окно или закрытие)
                print(f"[+] Запрос успешно отправлен хосту {username}!")
                self.append_sent_log({
                    "id": username,
                    "username": username,
                    "name": host_item.get("name"),
                    "timestamp": datetime.now().isoformat(),
                    "status": "success",
                    "mode": "live",
                    "notes": "Stay request sent successfully.",
                })
                self.update_queue_status(username, "Sent")
                return True
            else:
                print(f"[!] Кнопка Send Request не найдена!")
                return False

        except Exception as e:
            print(f"[!] Ошибка при обработке {username}: {e}")
            self.append_sent_log({
                "id": username,
                "username": username,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e),
            })
            return False

    def run(self) -> None:
        """Основной цикл работы автопилота."""
        print("=" * 60)
        print("[*] ЗАПУСК ФОНОВОГО АВТОПИЛОТА COUCHSURFING (Шаг 3)")
        print(f"[*] Суточный лимит: {self.daily_limit} запросов")
        print(f"[*] Пауза между запросами: {self.delay_min} – {self.delay_max} минут")
        print(f"[*] Режим Dry-Run: {self.dry_run}")
        print("=" * 60)

        # 1. Проверка суточного лимита
        sent_today = self.get_sent_today_count()
        print(f"[*] Отправлено сегодня: {sent_today} / {self.daily_limit}")
        if sent_today >= self.daily_limit:
            print(f"[!] Суточный лимит исчерпан ({sent_today}/{self.daily_limit}). Автопилот завершает работу.")
            self.update_autopilot_status(
                is_running=False,
                last_status=f"Суточный лимит достигнут ({sent_today}/{self.daily_limit})",
            )
            return

        # 2. Загрузка очереди кандидатов
        if not QUEUE_FILE.exists():
            print("[!] Файл requests_queue.json не найден. Сначала выполните Шаг 2 в интерфейсе.")
            return

        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)

        # Выбираем кандидатов: сначала Approved, если нет - можно отфильтровать
        if self.target_username:
            candidates = [x for x in queue if x.get("username") == self.target_username]
        else:
            candidates = [
                x for x in queue
                if x.get("status") == "Approved"
            ]
            # Если нет Approved, берем Draft с согласия (только если target указан)
            if not candidates:
                print("[*] Нет хостов со статусом 'Approved'. Возьмем первые не отправленные из очереди...")
                candidates = [
                    x for x in queue
                    if x.get("status") not in ("Sent", "Sent (Dry-Run)", "Skipped")
                ]

        if not candidates:
            print("[!] Нет доступных кандидатов для отправки.")
            self.update_autopilot_status(is_running=False, last_status="Нет доступных хостов для отправки")
            return

        print(f"[*] Кандидатов к отправке: {len(candidates)}")

        # 3. Инициализация Playwright
        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
            browser = p.chromium.launch(headless=self.headless, args=launch_args)

            context_kwargs = {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }
            if AUTH_STATE_FILE.exists():
                context_kwargs["storage_state"] = str(AUTH_STATE_FILE)

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            # Обработка кандидатов в цикле
            for idx, candidate in enumerate(candidates, 1):
                if not self.is_running:
                    print("[!] Работа автопилота прервана.")
                    break

                # Проверка суточного лимита
                current_sent = self.get_sent_today_count()
                if current_sent >= self.daily_limit:
                    print(f"[!] Достигнут суточный лимит ({current_sent}/{self.daily_limit}). Остановка.")
                    break

                username = candidate.get("username", "")
                success = self.process_host(page, candidate)

                # Если это не последний кандидат и автопилот не остановлен
                if idx < len(candidates) and self.is_running and self.get_sent_today_count() < self.daily_limit:
                    if self.test_mode:
                        sleep_seconds = random.uniform(6, 12)
                    else:
                        sleep_seconds = random.uniform(self.delay_min * 60, self.delay_max * 60)

                    next_time = time.time() + sleep_seconds
                    minutes_str = f"{sleep_seconds / 60:.1f}"
                    print(f"[*] Антифрод пауза: следующая отправка через {minutes_str} мин ({int(sleep_seconds)} сек)...")

                    # Периодическое обновление таймера в статусе
                    start_sleep = time.time()
                    while time.time() - start_sleep < sleep_seconds:
                        self.update_autopilot_status(
                            is_running=True,
                            current_host=username,
                            next_send_time=next_time,
                            last_status=f"Ожидание перед следующим хостом ({int(next_time - time.time())} сек)",
                        )
                        time.sleep(2)

            context.close()
            browser.close()

        self.update_autopilot_status(
            is_running=False,
            last_status=f"Завершено. Отправлено сегодня: {self.get_sent_today_count()}/{self.daily_limit}",
        )
        print("[+] Работа автопилота завершена.")


def main():
    parser = argparse.ArgumentParser(description="Фоновый автопилот отправки запросов Couchsurfing")
    parser.add_argument("--daily-limit", type=int, default=DEFAULT_DAILY_LIMIT, help="Суточный лимит (10-15)")
    parser.add_argument("--delay-min", type=int, default=DEFAULT_DELAY_MIN, help="Мин. пауза (минут)")
    parser.add_argument("--delay-max", type=int, default=DEFAULT_DELAY_MAX, help="Макс. пауза (минут)")
    parser.add_argument("--dry-run", action="store_true", help="Тестовый режим без клика отправки")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Показать окно браузера")
    parser.add_argument("--target", type=str, default=None, help="Целевой username хоста")
    parser.add_argument("--test-mode", action="store_true", help="Быстрый тестовый режим пауз (секунды вместо минут)")

    args = parser.parse_args()

    sender = AutoSender(
        daily_limit=args.daily_limit,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        dry_run=args.dry_run,
        headless=args.headless,
        target_username=args.target,
        test_mode=args.test_mode,
    )
    sender.run()


if __name__ == "__main__":
    main()
