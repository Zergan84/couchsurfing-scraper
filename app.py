"""
app.py - Веб-сервер управления парсером Couchsurfing и генератором запросов (FastAPI + Uvicorn).

Предоставляет:
- Веб-интерфейс на http://localhost:8000
- Вкладка 1: "Поиск и База хостов" (таблица хостов с Instagram, спальным местом, рейтингом)
- Вкладка 2: "Генератор запросов (Шаг 2)" (интерактивные карточки, строгая персонализация, 1-click copy, статусы, экспорт очереди)
- Управление сбором и глубокой фильтрацией (scraper.py, filter_hosts.py)
- Автосохранение в output/requests_queue.json
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from request_manager import (
    DEFAULT_CHECK_IN,
    DEFAULT_CHECK_OUT,
    DEFAULT_CONTEXT,
    QUEUE_FILE,
    RequestQueueManager,
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
USER_DATA_DIR = BASE_DIR / "user_data"

app = FastAPI(title="Couchsurfing Scraper & Request Generator Dashboard")
queue_manager = RequestQueueManager()

# Глобальное состояние выполняемого процесса
state = {
    "is_running": False,
    "current_task": "None",
    "process": None,
    "logs": [],
    "last_city": "tokyo",
}


class ScraperParams(BaseModel):
    city: str = "Tokyo"
    gender: str = "Any"
    status: str = "Accepting Guests"
    max_days: int = 7
    min_rate: float = 75.0
    pages: int = 10
    headless: bool = False


class FilterParams(BaseModel):
    gender: str = "any"
    allow_couples: bool = True
    enrich_home: bool = False


class CookieInput(BaseModel):
    cookie: str


class SaveRequestItem(BaseModel):
    username: str
    message: Optional[str] = None
    status: Optional[str] = None


class RegenerateItem(BaseModel):
    username: str
    check_in: str = DEFAULT_CHECK_IN
    check_out: str = DEFAULT_CHECK_OUT
    guest_context: str = DEFAULT_CONTEXT


class RegenerateAll(BaseModel):
    check_in: str = DEFAULT_CHECK_IN
    check_out: str = DEFAULT_CHECK_OUT
    guest_context: str = DEFAULT_CONTEXT
    overwrite_approved: bool = False


class AutopilotParams(BaseModel):
    daily_limit: int = 12
    delay_min: int = 15
    delay_max: int = 35
    dry_run: bool = False
    test_mode: bool = False
    target: Optional[str] = None


def log_message(msg: str):
    print(msg)
    state["logs"].append(msg)
    if len(state["logs"]) > 300:
        state["logs"].pop(0)


async def run_process_async(cmd: List[str], task_name: str):
    """Асинхронный запуск подпроцесса с потоковым чтением stdout/stderr."""
    state["is_running"] = True
    state["current_task"] = task_name
    log_message(f"[*] Запуск процесса: {' '.join(cmd)}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env=env,
        )
        state["process"] = proc

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                decoded = line.decode("utf-8", errors="replace").strip()
            except Exception:
                decoded = line.decode("cp1251", errors="replace").strip()
            if decoded:
                log_message(decoded)

        await proc.wait()
        log_message(f"[+] Задача '{task_name}' завершена с кодом {proc.returncode}")
        # После успешной фильтрации обновляем очередь
        if "фильтрация" in task_name.lower():
            queue_manager.initialize_queue()
    except Exception as e:
        log_message(f"[!] Ошибка выполнения задачи: {e}")
    finally:
        state["is_running"] = False
        state["current_task"] = "None"
        state["process"] = None


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Template index.html not found")
    return index_file.read_text(encoding="utf-8")


@app.get("/api/status")
async def get_status():
    """Текущий статус парсера, последние логи и количество результатов."""
    slug = state.get("last_city", "tokyo")
    json_path = OUTPUT_DIR / f"hosts_{slug}.json"
    curated_path = OUTPUT_DIR / f"hosts_{slug}_curated.json"

    total_hosts = 0
    curated_hosts = 0

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                total_hosts = len(json.load(f))
        except Exception:
            pass

    if curated_path.exists():
        try:
            with open(curated_path, "r", encoding="utf-8") as f:
                curated_hosts = len(json.load(f))
        except Exception:
            pass

    return {
        "is_running": state["is_running"],
        "current_task": state["current_task"],
        "logs": state["logs"][-60:],
        "total_hosts": total_hosts,
        "curated_hosts": curated_hosts,
    }


@app.post("/api/start_scraper")
async def start_scraper(params: ScraperParams):
    """Запуск scraper.py с переданными параметрами."""
    if state["is_running"]:
        return {"error": "Процесс уже выполняется!"}

    state["logs"] = []
    state["last_city"] = "".join(c if c.isalnum() else "_" for c in params.city.lower())

    cmd = [
        sys.executable,
        "-u",
        str(BASE_DIR / "scraper.py"),
        "--city", params.city,
        "--gender", params.gender,
        "--status", params.status,
        "--max-days", str(params.max_days),
        "--min-rate", str(params.min_rate),
        "--pages", str(params.pages),
    ]
    if params.headless:
        cmd.append("--headless")

    asyncio.create_task(run_process_async(cmd, "Сбор анкет"))
    return {"status": "started", "city": params.city}


@app.post("/api/start_filter")
async def start_filter(params: FilterParams):
    """Запуск filter_hosts.py для очистки датасета от неактивных хостов."""
    if state["is_running"]:
        return {"error": "Процесс уже выполняется!"}

    slug = state.get("last_city", "tokyo")
    input_file = OUTPUT_DIR / f"hosts_{slug}.json"
    if not input_file.exists():
        input_file = OUTPUT_DIR / "hosts_tokyo.json"
    if not input_file.exists():
        return {"error": "Сначала соберите анкеты (нет исходного JSON файла)!"}

    state["logs"] = []
    cmd = [
        sys.executable,
        "-u",
        str(BASE_DIR / "filter_hosts.py"),
        "--input", str(input_file),
        "--gender", params.gender,
    ]
    if not params.allow_couples:
        cmd.append("--no-couples")
    if params.enrich_home:
        cmd.append("--enrich-home")

    asyncio.create_task(run_process_async(cmd, "Глубокая фильтрация"))
    return {"status": "started"}


@app.post("/api/start_auth_console")
async def start_auth_console():
    """Запуск auth.py в новом видимом окне консоли Windows."""
    try:
        flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "auth.py")],
            cwd=str(BASE_DIR),
            creationflags=flags,
        )
        return {"status": "launched"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/set_cookie")
async def set_cookie(data: CookieInput):
    """Сохранение cookie напрямую."""
    raw = data.cookie.strip()
    if not raw:
        return {"error": "Cookie is empty"}

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    auth_state_path = USER_DATA_DIR / "auth_state.json"

    cookies_list = []
    if "=" in raw:
        pairs = raw.split(";")
        for p in pairs:
            p = p.strip()
            if "=" in p:
                k, v = p.split("=", 1)
                cookies_list.append({
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".couchsurfing.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                })
    else:
        cookies_list.append({
            "name": "_couchsurfing_session",
            "value": raw,
            "domain": ".couchsurfing.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        })

    storage_state_obj = {
        "cookies": cookies_list,
        "origins": [{"origin": "https://www.couchsurfing.com", "localStorage": []}],
    }

    with open(auth_state_path, "w", encoding="utf-8") as f:
        json.dump(storage_state_obj, f, indent=2)

    log_message(f"[+] Сохранен auth_state.json с {len(cookies_list)} cookies.")
    return {"status": "ok", "count": len(cookies_list)}


@app.post("/api/stop")
async def stop_process():
    """Остановка выполняющегося процесса."""
    proc = state.get("process")
    if proc:
        try:
            proc.terminate()
            log_message("[!] Процесс принудительно остановлен пользователем.")
        except Exception as e:
            log_message(f"[!] Ошибка остановки: {e}")
        state["is_running"] = False
        state["process"] = None
        return {"status": "stopped"}
    return {"status": "no_process"}


@app.get("/api/results")
async def get_results(curated: bool = False):
    """Возвращает список хостов (сырых или очищенных)."""
    slug = state.get("last_city", "tokyo")
    if curated:
        json_path = OUTPUT_DIR / f"hosts_{slug}_curated.json"
        if not json_path.exists():
            json_path = OUTPUT_DIR / "hosts_tokyo_curated.json"
    else:
        json_path = OUTPUT_DIR / f"hosts_{slug}.json"
        if not json_path.exists():
            json_path = OUTPUT_DIR / "hosts_tokyo.json"

    if not json_path.exists():
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@app.get("/api/download/csv")
async def download_csv(curated: bool = False):
    slug = state.get("last_city", "tokyo")
    target_name = f"hosts_{slug}_curated.csv" if curated else f"hosts_{slug}.csv"
    csv_path = OUTPUT_DIR / target_name
    if not csv_path.exists():
        fallback_name = "hosts_tokyo_curated.csv" if curated else "hosts_tokyo.csv"
        csv_path = OUTPUT_DIR / fallback_name
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV file not found")
    return FileResponse(path=csv_path, filename=csv_path.name, media_type="text/csv")


@app.get("/api/download/json")
async def download_json(curated: bool = False):
    slug = state.get("last_city", "tokyo")
    target_name = f"hosts_{slug}_curated.json" if curated else f"hosts_{slug}.json"
    json_path = OUTPUT_DIR / target_name
    if not json_path.exists():
        fallback_name = "hosts_tokyo_curated.json" if curated else "hosts_tokyo.json"
        json_path = OUTPUT_DIR / fallback_name
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="JSON file not found")
    return FileResponse(path=json_path, filename=json_path.name, media_type="application/json")


# =========================================================================
# Шаг 2: Эндпоинты генератора персонализированных запросов и очереди
# =========================================================================

@app.get("/api/requests/queue")
async def get_requests_queue():
    """Возвращает текущую очередь персонализированных запросов со статистикой."""
    queue = queue_manager.load_queue()
    stats = {
        "total": len(queue),
        "approved": sum(1 for x in queue if x.get("status") == "Approved"),
        "draft": sum(1 for x in queue if x.get("status") == "Draft"),
        "skipped": sum(1 for x in queue if x.get("status") == "Skipped"),
        "with_instagram": sum(1 for x in queue if bool(x.get("instagram_handle"))),
    }
    return {
        "queue": queue,
        "stats": stats,
        "default_check_in": DEFAULT_CHECK_IN,
        "default_check_out": DEFAULT_CHECK_OUT,
        "default_context": DEFAULT_CONTEXT,
    }


@app.post("/api/requests/save")
async def save_request_item(payload: SaveRequestItem):
    """Сохраняет отредактированный текст сообщения или статус карточки хоста."""
    updated = queue_manager.update_item(
        username=payload.username,
        message=payload.message,
        status=payload.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Host not found in queue")

    queue = queue_manager.load_queue()
    stats = {
        "total": len(queue),
        "approved": sum(1 for x in queue if x.get("status") == "Approved"),
        "draft": sum(1 for x in queue if x.get("status") == "Draft"),
        "skipped": sum(1 for x in queue if x.get("status") == "Skipped"),
    }
    return {"status": "saved", "item": updated, "stats": stats}


@app.post("/api/requests/regenerate")
async def regenerate_single_request(payload: RegenerateItem):
    """Перегенерирует персонализированный запрос для конкретного хоста."""
    updated = queue_manager.regenerate_item(
        username=payload.username,
        check_in=payload.check_in,
        check_out=payload.check_out,
        guest_context=payload.guest_context,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Host not found in queue")
    return {"status": "regenerated", "item": updated}


@app.post("/api/requests/regenerate_all")
async def regenerate_all_requests(payload: RegenerateAll):
    """Массовая перегенерация запросов для всех кандидатов с новыми параметрами."""
    queue = queue_manager.regenerate_all(
        check_in=payload.check_in,
        check_out=payload.check_out,
        guest_context=payload.guest_context,
        overwrite_approved=payload.overwrite_approved,
    )
    stats = {
        "total": len(queue),
        "approved": sum(1 for x in queue if x.get("status") == "Approved"),
        "draft": sum(1 for x in queue if x.get("status") == "Draft"),
        "skipped": sum(1 for x in queue if x.get("status") == "Skipped"),
    }
    return {"status": "ok", "total": len(queue), "stats": stats}


@app.get("/api/autopilot/status")
async def get_autopilot_status():
    """Возвращает текущий статус автопилота, обратный отсчет и отправленные за сегодня."""
    status_file = OUTPUT_DIR / "autopilot_status.json"
    sent_log_file = OUTPUT_DIR / "sent_log.json"

    sent_today = 0
    if sent_log_file.exists():
        try:
            with open(sent_log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
            today_str = datetime.now().date().isoformat()
            sent_today = len([
                x for x in logs
                if x.get("timestamp", "").startswith(today_str)
                and x.get("status") in ("success", "dry_run_success")
            ])
        except Exception:
            pass

    status_data = {
        "is_running": (state["current_task"] == "Автопилот"),
        "sent_today": sent_today,
        "daily_limit": 12,
        "next_send_time": None,
        "seconds_remaining": 0,
        "last_status": "Остановлен",
        "current_host": None,
        "dry_run": False,
    }

    if status_file.exists():
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                status_data.update(saved)
                # Перепроверяем с реальным состоянием процесса
                status_data["is_running"] = (state["current_task"] == "Автопилот")
                if status_data.get("next_send_time"):
                    rem = int(status_data["next_send_time"] - asyncio.get_event_loop().time())
                    status_data["seconds_remaining"] = max(0, int(status_data["next_send_time"] - __import__("time").time()))
        except Exception:
            pass

    return status_data


@app.post("/api/autopilot/start")
async def start_autopilot(params: AutopilotParams):
    """Запуск фонового автопилота отправки stay-requests."""
    if state["is_running"]:
        return {"error": f"Уже выполняется процесс: {state['current_task']}"}

    state["logs"] = []
    cmd = [
        sys.executable,
        "-u",
        str(BASE_DIR / "auto_sender.py"),
        "--daily-limit", str(params.daily_limit),
        "--delay-min", str(params.delay_min),
        "--delay-max", str(params.delay_max),
    ]
    if params.dry_run:
        cmd.append("--dry-run")
    if params.test_mode:
        cmd.append("--test-mode")
    if params.target:
        cmd.extend(["--target", params.target])

    asyncio.create_task(run_process_async(cmd, "Автопилот"))
    return {"status": "started", "dry_run": params.dry_run}


@app.post("/api/autopilot/stop")
async def stop_autopilot():
    """Остановка автопилота."""
    proc = state.get("process")
    if proc:
        try:
            proc.terminate()
            log_message("[!] Автопилот принудительно остановлен пользователем.")
        except Exception as e:
            log_message(f"[!] Ошибка остановки: {e}")
        state["is_running"] = False
        state["process"] = None

    status_file = OUTPUT_DIR / "autopilot_status.json"
    if status_file.exists():
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["is_running"] = False
            data["last_status"] = "Остановлен пользователем"
            data["seconds_remaining"] = 0
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    return {"status": "stopped"}


@app.get("/api/requests/export")
async def export_requests_queue():
    """Скачивание файла очереди requests_queue.json."""
    if not QUEUE_FILE.exists():
        queue_manager.initialize_queue()
    return FileResponse(
        path=QUEUE_FILE,
        filename="requests_queue.json",
        media_type="application/json",
    )


if __name__ == "__main__":
    print("[*] Запуск веб-сервера интерфейса управления на http://0.0.0.0:8000 (доступен локально и по Tailscale)")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
