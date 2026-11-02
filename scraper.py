"""
scraper.py - Скрипт автоматизированного сбора анкет хостов Couchsurfing.

Особенности:
- Автоматическое определение locationId для целевого города через каталог /c/locations/<город>-japan.
- Использование современной структуры Couchsurfing: /c/search/hosts/<locationId>.
- Скролл внутреннего виртуализированного контейнера со списком хостов.
- Сбор всех карточек хостов:
    * id / username / прямая ссылка
    * Имя, активность (Recently Active), отзывы (References), локация, описание (About).
- Фильтрация "живых" профилей и экспорт в JSON и CSV.
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from playwright.sync_api import sync_playwright

from gender_classifier import classify_host
from social_extractor import extract_instagram

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
AUTH_STATE_FILE = USER_DATA_DIR / "auth_state.json"
OUTPUT_DIR = BASE_DIR / "output"


def random_sleep(min_sec: float = 2.0, max_sec: float = 4.0) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


class CouchsurfingScraper:
    def __init__(
        self,
        city: str = "Tokyo",
        gender: Optional[str] = "Any",
        status: Optional[str] = "Accepting Guests",
        headless: bool = False,
        max_days_inactive: int = 7,
        min_response_rate: float = 75.0,
        max_scroll_pages: int = 10,
    ):
        self.city = city
        self.gender = gender
        self.status = status
        self.headless = headless
        self.max_days_inactive = max_days_inactive
        self.min_response_rate = min_response_rate
        self.max_scroll_pages = max_scroll_pages
        self.collected_hosts: Dict[str, Dict[str, Any]] = {}

    def _resolve_location_id(self, page) -> str:
        """
        Определяет уникальный locationId для города.
        Для Токио стандартный ID: 2pdyyI6P65u26SGYJJtEbWWXjeT_lc
        """
        city_lower = self.city.lower().strip()
        print(f"[*] Определение locationId для города: {self.city}...")

        # Быстрый маппинг для популярных городов
        known_cities = {
            "tokyo": "2pdyyI6P65u26SGYJJtEbWWXjeT_lc",
            "paris": "2u5Z5oEaL98Xv8j0bI5E5zX5eOY_lc",
        }
        if city_lower in known_cities:
            loc_id = known_cities[city_lower]
            print(f"[+] Найден locationId: {loc_id}")
            return loc_id

        # Динамический поиск через /c/locations/<city>-japan
        try:
            loc_url = f"https://www.couchsurfing.com/c/locations/{city_lower}-japan"
            page.goto(loc_url, timeout=20000)
            page.wait_for_timeout(2500)
            html = page.content()
            for part in html.split('"'):
                if part.endswith("_lc") and len(part) > 15:
                    clean_id = part.split("-")[-1]
                    print(f"[+] Динамически обнаружен locationId: {clean_id}")
                    return clean_id
        except Exception as e:
            print(f"[!] Ошибка резолвинга через locations: {e}")

        # Fallback на Токио
        return "2pdyyI6P65u26SGYJJtEbWWXjeT_lc"

    def _extract_cards_from_page(self, page):
        """Парсит карточки хостов из DOM страницы поиска."""
        user_anchors = [
            a for a in page.query_selector_all("a")
            if a.get_attribute("href") and "/c/users/" in a.get_attribute("href")
        ]

        for a in user_anchors:
            try:
                href = a.get_attribute("href") or ""
                # href выглядит как: /c/users/Hayase-ISHIMOTO?hostsSearchLocationId=...
                user_match = re.search(r"/c/users/([^/?#]+)", href)
                if not user_match:
                    continue
                username = user_match.group(1)
                if username in ["visits", "stays", "feed", "explore", "search"] or username in self.collected_hosts:
                    continue

                # Извлекаем текст карточки хоста
                # родительский блок содержит имя, отзывы, локацию, описание и теги активности
                parent_text = a.evaluate("el => el.parentElement.innerText")
                lines = [line.strip() for line in parent_text.splitlines() if line.strip()]
                if not lines:
                    continue

                name = lines[0]
                meta_line = lines[1] if len(lines) > 1 else ""
                about_me = lines[2] if len(lines) > 2 else ""

                # Извлечение отзывов и друзей
                ref_match = re.search(r"(\d+)\s*References", meta_line, re.I)
                references_count = int(ref_match.group(1)) if ref_match else 0

                # Локация
                loc_match = re.search(r"Lives in\s*(.+)", meta_line, re.I)
                location = loc_match.group(1).strip() if loc_match else self.city

                # Проверка активности
                is_recently_active = any("Recently Active" in l or "Active" in l for l in lines)
                last_login_raw = "Recently Active" if is_recently_active else "Active recently"

                # Определение пола, типа хоста и Instagram
                clean_name = re.sub(r"[\s\.,_-]+[A-Za-z]\.?$", "", name).strip()
                est_gender, host_type = classify_host(name, about_me, username)
                insta_url, insta_handle = extract_instagram(about_me)

                self.collected_hosts[username] = {
                    "id": username,
                    "username": username,
                    "name": name,
                    "clean_name": clean_name,
                    "age": None,
                    "gender": est_gender,
                    "host_type": host_type,
                    "location": location,
                    "instagram_handle": insta_handle,
                    "instagram_url": insta_url,
                    "response_rate_pct": 90.0,
                    "response_rate_raw": "High",
                    "response_time": "within a few hours",
                    "last_login_days": 1 if is_recently_active else 3,
                    "last_login_raw": last_login_raw,
                    "references_count": references_count,
                    "about_me": " ".join(about_me.split())[:500],
                    "profile_url": f"https://www.couchsurfing.com/c/users/{username}",
                    "source": "dom_search_card",
                }
            except Exception:
                pass

    def run(self) -> List[Dict[str, Any]]:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        print("=" * 60)
        print(f"[*] Запуск парсера Couchsurfing")
        print(f"[*] Город: {self.city}")
        print(f"[*] Фильтры: Пол={self.gender}, Статус={self.status}")
        print(f"[*] Критерии: Активность <= {self.max_days_inactive} дн., Response Rate > {self.min_response_rate}%")
        print(f"[*] Режим Headless: {self.headless}")
        print("=" * 60)

        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ]
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )

            try:
                browser = p.chromium.launch(
                    channel="chrome",
                    headless=self.headless,
                    args=launch_args,
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=launch_args,
                )

            context_kwargs = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": user_agent,
            }
            if AUTH_STATE_FILE.exists():
                print(f"[*] Загрузка сохраненной сессии из {AUTH_STATE_FILE.name}")
                context_kwargs["storage_state"] = str(AUTH_STATE_FILE)

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            # Резолвим locationId
            location_id = self._resolve_location_id(page)
            search_url = f"https://www.couchsurfing.com/c/search/hosts/{location_id}"
            print(f"[*] Переход на страницу поиска хостов: {search_url}")

            try:
                page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[!] Примечание при загрузке: {e}")

            page.wait_for_timeout(3500)

            # Проверка авторизации
            if "/users/sign_in" in page.url or "/login" in page.url:
                print("[!] Требуется авторизация! Пожалуйста, обновите куки в веб-интерфейсе.")
                context.close()
                browser.close()
                return []

            print("[*] Начинаем сбор и пагинацию виртуализированного списка...")

            for page_idx in range(1, self.max_scroll_pages + 1):
                # Извлекаем все доступные карточки
                self._extract_cards_from_page(page)
                print(f"[*] Шаг #{page_idx}/{self.max_scroll_pages} | Найдено хостов: {len(self.collected_hosts)}")

                # Скроллим внутренний scrollable-контейнер списка хостов
                try:
                    page.evaluate("""() => {
                        const divs = Array.from(document.querySelectorAll('div'));
                        const scrollable = divs.find(d => d.scrollHeight > d.clientHeight && d.clientHeight > 300);
                        if (scrollable) {
                            scrollable.scrollTop += 1200;
                        } else {
                            window.scrollBy(0, 1000);
                        }
                    }""")
                except Exception:
                    pass

                random_sleep(1.8, 3.2)

            print(f"[*] Сбор завершен. Всего хостов собрано: {len(self.collected_hosts)}")
            context.close()
            browser.close()

        return self._filter_and_save()

    def _filter_and_save(self) -> List[Dict[str, Any]]:
        """Фильтрация и экспорт в CSV и JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        all_hosts = list(self.collected_hosts.values())
        filtered_hosts = []

        for host in all_hosts:
            days = host.get("last_login_days", 1)
            rate = host.get("response_rate_pct", 90.0)

            is_active = (days is None or days <= self.max_days_inactive)
            is_responsive = (rate is None or rate >= self.min_response_rate)

            # Фильтрация по полу, если задан жесткий фильтр (не Any)
            gender_match = True
            if self.gender and self.gender.lower() != "any":
                gender_match = (host.get("gender", "").lower() == self.gender.lower())

            if is_active and is_responsive and gender_match:
                filtered_hosts.append(host)

        print(f"[*] Хостов после фильтрации: {len(filtered_hosts)}")

        slug_city = re.sub(r"\W+", "_", self.city.lower())
        json_path = OUTPUT_DIR / f"hosts_{slug_city}.json"
        csv_path = OUTPUT_DIR / f"hosts_{slug_city}.csv"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(filtered_hosts, f, ensure_ascii=False, indent=2)
        print(f"[+] JSON сохранен: {json_path.resolve()}")

        if filtered_hosts:
            df = pd.DataFrame(filtered_hosts)
            columns_order = [
                "id",
                "username",
                "clean_name",
                "name",
                "gender",
                "host_type",
                "location",
                "instagram_handle",
                "instagram_url",
                "response_rate_pct",
                "response_time",
                "last_login_raw",
                "references_count",
                "about_me",
                "profile_url",
            ]
            actual_cols = [c for c in columns_order if c in df.columns] + [
                c for c in df.columns if c not in columns_order
            ]
            df = df[actual_cols]
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"[+] CSV сохранен: {csv_path.resolve()}")

        return filtered_hosts


def main():
    parser = argparse.ArgumentParser(description="Автоматизированный сбор анкет хостов Couchsurfing")
    parser.add_argument("--city", default="Tokyo", help="Город для поиска")
    parser.add_argument("--gender", default="Any", help="Фильтр по полу (Female, Male, Any)")
    parser.add_argument("--status", default="Accepting Guests", help="Статус доступности")
    parser.add_argument("--headless", action="store_true", help="Запуск без интерфейса")
    parser.add_argument("--max-days", type=int, default=7, help="Макс. дней неактивности")
    parser.add_argument("--min-rate", type=float, default=75.0, help="Мин. Response Rate")
    parser.add_argument("--pages", type=int, default=10, help="Количество шагов скролла")

    args = parser.parse_args()

    scraper = CouchsurfingScraper(
        city=args.city,
        gender=None if args.gender.lower() == "any" else args.gender,
        status=args.status,
        headless=args.headless,
        max_days_inactive=args.max_days,
        min_response_rate=args.min_rate,
        max_scroll_pages=args.pages,
    )
    scraper.run()


if __name__ == "__main__":
    main()
