"""Cross-platform process orchestrator for the financial data collectors."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import secrets
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Optional

import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from werkzeug.serving import make_server

try:
    from winotify import Notification
except ImportError:
    Notification = None

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
HEARTBEAT_PATH = BASE_DIR / "heartbeat.json"
CONTROL_PATH = BASE_DIR / ".orchestrator_control.json"
LOGGER = logging.getLogger("orchestrator")
UTC = timezone.utc

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        required = {
            "DB_HOST": os.getenv("DB_HOST", "").strip(),
            "DB_PASSWORD": os.getenv("DB_PASSWORD", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            db_host=required["DB_HOST"],
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "investor_db"),
            db_user=os.getenv("DB_USER", "investor_app"),
            db_password=required["DB_PASSWORD"],
            port=int(os.getenv("ORCHESTRATOR_PORT", "8090")),
        )


@dataclass
class WorkerState:
    name: str
    script: Path
    executable: Optional[Path] = None
    process: Optional[subprocess.Popen] = None
    status: str = "stopped"
    last_restart_time: Optional[str] = None
    restart_times: deque[datetime] = field(default_factory=deque)
    log_handle: Any = None

    @property
    def pid(self) -> Optional[int]:
        return self.process.pid if self.process and self.process.poll() is None else None

    def prune_restarts(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        while self.restart_times and self.restart_times[0] < cutoff:
            self.restart_times.popleft()

    @property
    def restart_count(self) -> int:
        self.prune_restarts()
        return len(self.restart_times)


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file_handler = TimedRotatingFileHandler(
        LOGS_DIR / "orchestrator.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    LOGGER.addHandler(console)
    LOGGER.addHandler(file_handler)
    LOGGER.propagate = False


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def send_notification(title: str, message: str) -> None:
    LOGGER.info("Notification: %s - %s", title, message)
    try:
        if os.name == "nt" and Notification is not None:
            Notification(app_id="Investor Data Collector", title=title, msg=message).show()
        elif sys.platform == "darwin":
            safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
            safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{safe_message}" with title "{safe_title}"',
                ],
                check=False,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        LOGGER.exception("Desktop notification failed")


class Orchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workers = {
            "news_scraper": WorkerState("news_scraper", BASE_DIR / "news_scraper.py"),
            "market_data": WorkerState("market_data", BASE_DIR / "market_data.py"),
            "ai_engine": WorkerState(
                "ai_engine",
                BASE_DIR.parent / "ai_engine" / "engine_runner.py",
                BASE_DIR.parent / "ai_engine" / "venv" / "bin" / "python",
            ),
        }
        self.shutdown_event = threading.Event()
        self.lock = threading.RLock()
        self.stop_lock = threading.Lock()
        self.control_token = secrets.token_urlsafe(32)
        self.db_connected: Optional[bool] = None
        self.latest_metrics: dict[str, Any] = self.empty_metrics()
        self.server = None

    @staticmethod
    def empty_metrics() -> dict[str, Any]:
        return {
            "db_connected": False,
            "db_articles_today": None,
            "db_prices_today": None,
            "last_news_write": None,
            "last_price_write": None,
            "last_engine_write": None,
        }

    def start_worker(self, name: str, is_restart: bool = False) -> None:
        worker = self.workers[name]
        with self.lock:
            if worker.process and worker.process.poll() is None:
                return
            if not worker.script.exists():
                worker.status = "failed"
                send_notification("Worker FAILED", f"{name}: script not found")
                return
            if worker.executable and not worker.executable.exists():
                worker.status = "failed"
                send_notification("Worker FAILED", f"{name}: Python executable not found")
                return
            if is_restart:
                worker.prune_restarts()
                if worker.restart_count >= 3:
                    worker.status = "failed"
                    send_notification(
                        "Worker FAILED",
                        f"{name} reached 3 restarts within one hour",
                    )
                    return
                worker.restart_times.append(datetime.now(UTC))
                worker.last_restart_time = datetime.now(UTC).isoformat()

            worker.log_handle = open(
                LOGS_DIR / f"{name}_process.log", "a", encoding="utf-8", buffering=1
            )
            creationflags = 0
            start_new_session = False
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                start_new_session = True
            worker.process = subprocess.Popen(
                [str(worker.executable or sys.executable), str(worker.script)],
                cwd=str(worker.script.parent),
                stdout=worker.log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
            worker.status = "running"
            LOGGER.info("Started %s with PID %s", name, worker.process.pid)

    def terminate_worker(self, name: str, mark_stopped: bool = True) -> None:
        worker = self.workers[name]
        with self.lock:
            process = worker.process
            if process and process.poll() is None:
                LOGGER.info("Stopping %s PID %s", name, process.pid)
                if os.name == "nt":
                    try:
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    except Exception:
                        process.terminate()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    LOGGER.warning("%s did not stop gracefully; killing it", name)
                    if os.name == "nt":
                        process.kill()
                    else:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait(timeout=10)
            worker.process = None
            if worker.log_handle:
                worker.log_handle.close()
                worker.log_handle = None
            if mark_stopped:
                worker.status = "stopped"

    def restart_worker(self, name: str, manual: bool = False) -> bool:
        if name not in self.workers:
            return False
        self.terminate_worker(name)
        worker = self.workers[name]
        if manual:
            worker.restart_times.clear()
            worker.status = "stopped"
        self.start_worker(name, is_restart=not manual)
        self.write_heartbeat()
        return worker.status == "running"

    def monitor_workers(self) -> None:
        while not self.shutdown_event.wait(30):
            for name, worker in self.workers.items():
                with self.lock:
                    crashed = (
                        worker.status == "running"
                        and worker.process is not None
                        and worker.process.poll() is not None
                    )
                    exit_code = worker.process.poll() if crashed else None
                if crashed:
                    LOGGER.error("%s crashed with exit code %s", name, exit_code)
                    send_notification("Worker crashed", f"{name} exited with code {exit_code}")
                    self.terminate_worker(name, mark_stopped=False)
                    self.start_worker(name, is_restart=True)
            self.refresh_metrics()

    def query_db_metrics(self) -> dict[str, Any]:
        connection = psycopg2.connect(
            host=self.settings.db_host,
            port=self.settings.db_port,
            dbname=self.settings.db_name,
            user=self.settings.db_user,
            password=self.settings.db_password,
            connect_timeout=10,
            application_name="collector_orchestrator",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM news_articles
                         WHERE fetched_at::date = CURRENT_DATE),
                        (SELECT COUNT(*) FROM market_prices
                         WHERE fetched_at::date = CURRENT_DATE),
                        (SELECT MAX(fetched_at) FROM news_articles),
                        (SELECT MAX(fetched_at) FROM market_prices),
                        (SELECT MAX(analyzed_at) FROM sentiment_scores)
                    """
                )
                articles, prices, last_news, last_price, last_engine = cursor.fetchone()
                return {
                    "db_connected": True,
                    "db_articles_today": articles,
                    "db_prices_today": prices,
                    "last_news_write": last_news.isoformat() if last_news else None,
                    "last_price_write": last_price.isoformat() if last_price else None,
                    "last_engine_write": last_engine.isoformat() if last_engine else None,
                }
        finally:
            connection.close()

    def refresh_metrics(self) -> None:
        try:
            metrics = self.query_db_metrics()
            if self.db_connected is False:
                send_notification("Database restored", "PostgreSQL connection restored")
            self.db_connected = True
            self.latest_metrics = metrics
        except Exception as exc:
            LOGGER.error("Database status query failed: %s", exc)
            if self.db_connected is not False:
                send_notification("Database connection lost", str(exc))
            self.db_connected = False
            self.latest_metrics = self.empty_metrics()

    def status_payload(self) -> dict[str, Any]:
        with self.lock:
            workers = {}
            for name, worker in self.workers.items():
                workers[name] = {
                    "status": worker.status,
                    "pid": worker.pid,
                    "last_restart_time": worker.last_restart_time,
                    "restart_count": worker.restart_count,
                    "last_successful_db_write": {
                        "news_scraper": self.latest_metrics["last_news_write"],
                        "market_data": self.latest_metrics["last_price_write"],
                        "ai_engine": self.latest_metrics["last_engine_write"],
                    }.get(name),
                }
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "workers": workers,
                **self.latest_metrics,
            }

    def heartbeat_payload(self) -> dict[str, Any]:
        status = self.status_payload()
        return {
            "timestamp": status["timestamp"],
            "workers": {
                name: {
                    "status": value["status"],
                    "pid": value["pid"],
                    "restarts": value["restart_count"],
                }
                for name, value in status["workers"].items()
            },
            "db_articles_today": status["db_articles_today"],
            "db_prices_today": status["db_prices_today"],
        }

    def write_heartbeat(self) -> None:
        atomic_json_write(HEARTBEAT_PATH, self.heartbeat_payload())

    def heartbeat_loop(self) -> None:
        while not self.shutdown_event.is_set():
            self.refresh_metrics()
            self.write_heartbeat()
            if self.shutdown_event.wait(300):
                break

    def write_control_file(self) -> None:
        atomic_json_write(
            CONTROL_PATH,
            {
                "pid": os.getpid(),
                "port": self.settings.port,
                "token": self.control_token,
                "started_at": datetime.now(UTC).isoformat(),
            },
        )

    def start_all(self) -> None:
        self.write_control_file()
        for name in self.workers:
            self.start_worker(name)
        self.refresh_metrics()
        self.write_heartbeat()
        send_notification("Collector orchestrator started", "All collector workers started")

    def stop_all(self) -> None:
        with self.stop_lock:
            self.shutdown_event.set()
            for name in self.workers:
                self.terminate_worker(name)
            self.write_heartbeat()
            CONTROL_PATH.unlink(missing_ok=True)

def render_status_html(payload: dict[str, Any]) -> str:
    rows = ""
    for name, worker in payload["workers"].items():
        rows += f"""
        <tr>
          <td>{name}</td><td class="{worker['status']}">{worker['status']}</td>
          <td>{worker['pid'] or '-'}</td><td>{worker['restart_count']}</td>
          <td>{worker['last_restart_time'] or '-'}</td>
          <td>{worker['last_successful_db_write'] or '-'}</td>
        </tr>"""
    return f"""<!doctype html>
<html><head><title>Collector Orchestrator</title>
<meta http-equiv="refresh" content="30">
<style>
body{{font-family:Segoe UI,Arial;background:#101827;color:#e5e7eb;padding:30px}}
table{{border-collapse:collapse;width:100%;background:#172033}}
th,td{{padding:12px;border-bottom:1px solid #334155;text-align:left}}
.running{{color:#34d399}} .failed{{color:#fb7185}} .stopped{{color:#fbbf24}}
.cards{{display:flex;gap:16px;margin:20px 0}} .card{{background:#172033;padding:18px;border-radius:8px}}
</style></head><body>
<h1>Financial Data Collector Orchestrator</h1>
<div class="cards">
<div class="card">News articles today: <strong>{payload['db_articles_today']}</strong></div>
<div class="card">Price records today: <strong>{payload['db_prices_today']}</strong></div>
<div class="card">Database: <strong>{'connected' if payload['db_connected'] else 'offline'}</strong></div>
</div>
<table><thead><tr><th>Worker</th><th>Status</th><th>PID</th><th>Restarts/hour</th>
<th>Last restart</th><th>Last successful DB write</th></tr></thead><tbody>{rows}</tbody></table>
<p>Updated: {payload['timestamp']}</p>
</body></html>"""


def create_app(orchestrator: Orchestrator) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def status_page() -> Response:
        return Response(render_status_html(orchestrator.status_payload()), mimetype="text/html")

    @app.get("/api/status")
    def api_status():
        return jsonify(orchestrator.status_payload())

    @app.post("/api/control/stop")
    def api_stop():
        if request.headers.get("X-Control-Token") != orchestrator.control_token:
            return jsonify({"error": "unauthorized"}), 401
        threading.Thread(target=orchestrator.stop_all, daemon=True).start()
        return jsonify({"status": "stopping"})

    @app.post("/api/control/restart/<worker_name>")
    def api_restart(worker_name: str):
        if request.headers.get("X-Control-Token") != orchestrator.control_token:
            return jsonify({"error": "unauthorized"}), 401
        if worker_name not in orchestrator.workers:
            return jsonify({"error": "unknown worker"}), 404
        success = orchestrator.restart_worker(worker_name, manual=True)
        return jsonify({"worker": worker_name, "status": "running" if success else "failed"})

    return app


def load_control() -> dict[str, Any]:
    if not CONTROL_PATH.exists():
        raise RuntimeError("Orchestrator is not running or control file is missing")
    return json.loads(CONTROL_PATH.read_text(encoding="utf-8"))


def control_request(path: str) -> dict[str, Any]:
    control = load_control()
    response = requests.post(
        f"http://127.0.0.1:{control['port']}{path}",
        headers={"X-Control-Token": control["token"]},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def ensure_no_running_instance() -> None:
    if not CONTROL_PATH.exists():
        return
    try:
        control = load_control()
        response = requests.get(
            f"http://127.0.0.1:{control['port']}/api/status",
            timeout=3,
        )
    except Exception:
        LOGGER.warning("Removing stale orchestrator control file")
        CONTROL_PATH.unlink(missing_ok=True)
        return
    if response.ok:
        raise RuntimeError(f"Orchestrator is already running on port {control['port']}")
    LOGGER.warning("Removing stale orchestrator control file")
    CONTROL_PATH.unlink(missing_ok=True)


def command_start() -> int:
    configure_logging()
    try:
        ensure_no_running_instance()
        settings = Settings.from_env()
        orchestrator = Orchestrator(settings)
        orchestrator.start_all()
        app = create_app(orchestrator)
        orchestrator.server = make_server("0.0.0.0", settings.port, app, threaded=True)
        orchestrator.server.timeout = 1
        monitor = threading.Thread(target=orchestrator.monitor_workers, daemon=True)
        heartbeat = threading.Thread(target=orchestrator.heartbeat_loop, daemon=True)
        monitor.start()
        heartbeat.start()

        def request_shutdown(signum: int, frame: Any) -> None:
            del frame
            LOGGER.info("Shutdown requested by signal %s", signum)
            orchestrator.shutdown_event.set()

        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, request_shutdown)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, request_shutdown)

        LOGGER.info("Status server listening on http://0.0.0.0:%s", settings.port)
        while not orchestrator.shutdown_event.is_set():
            orchestrator.server.handle_request()
    except KeyboardInterrupt:
        LOGGER.info("CTRL+C received")
        orchestrator.stop_all()
    except Exception:
        LOGGER.exception("Orchestrator startup failed")
        if "orchestrator" in locals():
            orchestrator.stop_all()
        return 1
    finally:
        if "orchestrator" in locals():
            orchestrator.stop_all()
    return 0


def command_stop() -> int:
    try:
        print(json.dumps(control_request("/api/control/stop"), indent=2))
        return 0
    except Exception as exc:
        print(f"Unable to stop orchestrator: {exc}", file=sys.stderr)
        return 1


def command_status() -> int:
    if not HEARTBEAT_PATH.exists():
        print("heartbeat.json does not exist; orchestrator has not written status yet")
        return 1
    print(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    return 0


def command_restart(worker_name: str) -> int:
    try:
        print(json.dumps(control_request(f"/api/control/restart/{worker_name}"), indent=2))
        return 0
    except Exception as exc:
        print(f"Unable to restart {worker_name}: {exc}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Financial collector process orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start")
    subparsers.add_parser("stop")
    subparsers.add_parser("status")
    restart_parser = subparsers.add_parser("restart")
    restart_parser.add_argument("worker", choices=("news_scraper", "market_data", "ai_engine"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "start":
        return command_start()
    if args.command == "stop":
        return command_stop()
    if args.command == "status":
        return command_status()
    return command_restart(args.worker)


if __name__ == "__main__":
    raise SystemExit(main())
