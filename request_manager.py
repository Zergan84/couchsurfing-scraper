"""
request_manager.py - Управление очередью персонализированных запросов к хостам.
Обеспечивает синхронизацию с output/requests_queue.json и генерацию текстов.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from message_generator import generate_stay_request

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
QUEUE_FILE = OUTPUT_DIR / "requests_queue.json"
CURATED_FILE = OUTPUT_DIR / "hosts_tokyo_curated.json"
RAW_FILE = OUTPUT_DIR / "hosts_tokyo.json"

DEFAULT_CHECK_IN = "2026-11-11"
DEFAULT_CHECK_OUT = "2026-11-14"
DEFAULT_CONTEXT = (
    "Andrey, professional ski instructor heading to Club Med Tomamu (Hokkaido) "
    "for the winter season. 10+ years on Couchsurfing, tidy, independent, loves "
    "mountains, sports, authentic local food and respectful cultural exchange. "
    "Spends daytime out exploring the city."
)


class RequestQueueManager:
    def __init__(self, queue_file: Path = QUEUE_FILE):
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

    def load_queue(self) -> List[Dict[str, Any]]:
        """Загружает очередь из файла или инициализирует её из hosts_tokyo_curated.json."""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Инициализация очереди из очищенных хостов
        return self.initialize_queue()

    def initialize_queue(
        self,
        check_in: str = DEFAULT_CHECK_IN,
        check_out: str = DEFAULT_CHECK_OUT,
        guest_context: str = DEFAULT_CONTEXT,
    ) -> List[Dict[str, Any]]:
        """Создает начальную очередь запросов для всех валидных хостов."""
        source_file = CURATED_FILE if CURATED_FILE.exists() else RAW_FILE
        if not source_file.exists():
            return []

        try:
            with open(source_file, "r", encoding="utf-8") as f:
                hosts = json.load(f)
        except Exception:
            return []

        queue = []
        for h in hosts:
            username = h.get("username", "")
            if not username:
                continue

            msg = generate_stay_request(
                host=h,
                check_in=check_in,
                check_out=check_out,
                guest_context=guest_context,
            )

            item = {
                "id": username,
                "username": username,
                "name": h.get("name", ""),
                "clean_name": h.get("clean_name") or h.get("name", ""),
                "estimated_gender": h.get("estimated_gender") or h.get("gender", "Unknown"),
                "host_type": h.get("host_type", "solo"),
                "location": h.get("location", "Tokyo"),
                "sleeping_arrangement": h.get("sleeping_arrangement", "Not specified"),
                "house_rules": h.get("house_rules", "Standard house rules"),
                "profile_url": h.get("profile_url") or f"https://www.couchsurfing.com/c/users/{username}",
                "stay_request_url": f"https://www.couchsurfing.com/c/users/{username}/stay-request",
                "instagram_handle": h.get("instagram_handle", ""),
                "instagram_url": h.get("instagram_url", ""),
                "references_count": h.get("references_count", 0),
                "response_rate_pct": h.get("response_rate_pct", 90.0),
                "secret_code_detected": h.get("secret_code_detected", False),
                "secret_code_hint": h.get("secret_code_hint", ""),
                "about_me_clean": h.get("about_me_clean") or h.get("about_me", ""),
                "check_in": check_in,
                "check_out": check_out,
                "guest_context": guest_context,
                "generated_message": msg,
                "status": "Draft",  # Draft | Approved | Skipped
                "updated_at": datetime.now().isoformat(),
            }
            queue.append(item)

        self.save_queue(queue)
        return queue

    def save_queue(self, queue: List[Dict[str, Any]]) -> None:
        """Сохраняет очередь на диск."""
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

    def update_item(
        self,
        username: str,
        message: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Обновляет статус и/или отредактированный текст для хоста."""
        queue = self.load_queue()
        target = None
        for item in queue:
            if item.get("username") == username:
                if message is not None:
                    item["generated_message"] = message
                if status is not None:
                    item["status"] = status
                item["updated_at"] = datetime.now().isoformat()
                target = item
                break

        if target:
            self.save_queue(queue)
        return target

    def regenerate_item(
        self,
        username: str,
        check_in: str = DEFAULT_CHECK_IN,
        check_out: str = DEFAULT_CHECK_OUT,
        guest_context: str = DEFAULT_CONTEXT,
    ) -> Optional[Dict[str, Any]]:
        """Перегенерирует сообщение для конкретного хоста."""
        queue = self.load_queue()
        target = None
        for item in queue:
            if item.get("username") == username:
                item["check_in"] = check_in
                item["check_out"] = check_out
                item["guest_context"] = guest_context
                item["generated_message"] = generate_stay_request(
                    host=item,
                    check_in=check_in,
                    check_out=check_out,
                    guest_context=guest_context,
                )
                item["updated_at"] = datetime.now().isoformat()
                target = item
                break

        if target:
            self.save_queue(queue)
        return target

    def regenerate_all(
        self,
        check_in: str = DEFAULT_CHECK_IN,
        check_out: str = DEFAULT_CHECK_OUT,
        guest_context: str = DEFAULT_CONTEXT,
        overwrite_approved: bool = False,
    ) -> List[Dict[str, Any]]:
        """Перегенерирует сообщения для всех хостов в очереди."""
        queue = self.load_queue()
        for item in queue:
            if not overwrite_approved and item.get("status") == "Approved":
                continue

            item["check_in"] = check_in
            item["check_out"] = check_out
            item["guest_context"] = guest_context
            item["generated_message"] = generate_stay_request(
                host=item,
                check_in=check_in,
                check_out=check_out,
                guest_context=guest_context,
            )
            item["updated_at"] = datetime.now().isoformat()

        self.save_queue(queue)
        return queue
