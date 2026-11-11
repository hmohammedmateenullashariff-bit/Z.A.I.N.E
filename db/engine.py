"""
db/engine.py
Hardened SQLite Database Engine for Project-Z (Z.A.I.N.E).
Enforces:
- PRAGMA journal_mode=WAL
- PRAGMA synchronous=NORMAL
- PRAGMA busy_timeout=5000
- PRAGMA foreign_keys=ON
- Dedicated single-writer queue to serialize database writes and prevent 'database is locked' errors
- Zero-lock JSONL blackbox fallback on catastrophic write contention.
"""

import atexit
import json
import logging
import os
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("zaine.db.engine")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "zaine_tasks.db"
BLACKBOX_LOG_PATH = PROJECT_ROOT / "data" / "failure_blackbox.jsonl"


class DatabaseEngine:
    _instance: Optional["DatabaseEngine"] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        BLACKBOX_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        self._write_queue: queue.Queue = queue.Queue(maxsize=10000)
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="ZaineDBWriter",
            daemon=True
        )
        self._init_pragmas()
        self._writer_thread.start()
        atexit.register(self.shutdown)

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "DatabaseEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db_path)
            return cls._instance

    def _init_pragmas(self) -> None:
        """Sets WAL mode and concurrency pragmas on the database file."""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.commit()
            conn.close()
            logger.info("Initialized SQLite WAL mode & busy_timeout=5000 on %s", self.db_path.name)
        except Exception as e:
            logger.error("Failed to initialize PRAGMAs on %s: %s", self.db_path, e)
            self._write_blackbox("INIT_PRAGMAS", str(e), {"db_path": str(self.db_path)})

    def _writer_loop(self) -> None:
        """Dedicated writer thread loop that serializes all DB mutations."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception as e:
            self._write_blackbox("WRITER_CONNECT_FAIL", str(e), {})

        while self._running or not self._write_queue.empty():
            try:
                task = self._write_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if task is None:
                self._write_queue.task_done()
                break

            sql, params, done_event, result_box, is_script = task
            try:
                if conn is None:
                    conn = sqlite3.connect(str(self.db_path), timeout=5.0)
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA busy_timeout=5000;")

                cursor = conn.cursor()
                if is_script:
                    cursor.executescript(sql)
                    last_id = None
                    rowcount = -1
                else:
                    cursor.execute(sql, params)
                    last_id = cursor.lastrowid
                    rowcount = cursor.rowcount
                conn.commit()
                result_box["success"] = True
                result_box["lastrowid"] = last_id
                result_box["rowcount"] = rowcount
            except Exception as exc:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                result_box["success"] = False
                result_box["error"] = str(exc)
                logger.error("Database write error: %s | Query: %s", exc, sql[:100])
                self._write_blackbox("WRITE_FAILURE", str(exc), {"sql": sql[:400], "params": str(params)[:200]})
            finally:
                done_event.set()
                self._write_queue.task_done()

        if conn:
            try:
                conn.close()
            except Exception:
                pass

    def _write_blackbox(self, event_type: str, message: str, meta: Dict[str, Any]) -> None:
        """Appends a failure event to the zero-lock JSONL blackbox file."""
        try:
            entry = {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "message": message[:400],
                "meta": meta
            }
            with open(BLACKBOX_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.critical("Fatal: Unable to write to JSONL blackbox: %s", e)

    def execute_write(self, sql: str, params: Tuple[Any, ...] = (), timeout: float = 10.0) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Submits a write operation to the serialized queue.
        Returns: (success: bool, lastrowid: Optional[int], error_message: Optional[str])
        """
        done_event = threading.Event()
        result_box: Dict[str, Any] = {}
        self._write_queue.put((sql, params, done_event, result_box, False))
        
        finished = done_event.wait(timeout=timeout)
        if not finished:
            err = f"Write operation timed out after {timeout}s: {sql[:80]}"
            self._write_blackbox("WRITE_TIMEOUT", err, {"sql": sql[:200]})
            return False, None, err

        if result_box.get("success"):
            return True, result_box.get("lastrowid"), None
        return False, None, result_box.get("error")

    def execute_script(self, script_sql: str, timeout: float = 15.0) -> Tuple[bool, Optional[str]]:
        """Submits a multi-statement DDL/script to the writer queue."""
        done_event = threading.Event()
        result_box: Dict[str, Any] = {}
        self._write_queue.put((script_sql, (), done_event, result_box, True))
        finished = done_event.wait(timeout=timeout)
        if not finished:
            err = f"Script execution timed out after {timeout}s"
            self._write_blackbox("SCRIPT_TIMEOUT", err, {})
            return False, err
        if result_box.get("success"):
            return True, None
        return False, result_box.get("error")

    def execute_read(self, sql: str, params: Tuple[Any, ...] = (), timeout: float = 5.0) -> List[Tuple]:
        """Executes a read query with snapshot isolation under WAL mode."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=timeout)
            conn.execute("PRAGMA busy_timeout=5000;")
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return rows
        except Exception as exc:
            logger.error("Database read error: %s | Query: %s", exc, sql[:100])
            self._write_blackbox("READ_FAILURE", str(exc), {"sql": sql[:400], "params": str(params)[:200]})
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def shutdown(self) -> None:
        """Flushes write queue and shuts down background writer."""
        if not self._running:
            return
        self._running = False
        self._write_queue.put(None)
        if self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)


def get_db_engine(db_path: Optional[Path] = None) -> DatabaseEngine:
    """Helper singleton factory."""
    return DatabaseEngine.get_instance(db_path)

