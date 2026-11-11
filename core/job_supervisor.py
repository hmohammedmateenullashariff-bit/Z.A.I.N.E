"""
core/job_supervisor.py
Armory Job Supervisor and Decoupled Telemetry Event Bus for Project-Z (Z.A.I.N.E).
Implements Claude Sonnet 5.5 backend criteria:
- Supervised OS subprocesses started in separate process groups (CREATE_NEW_PROCESS_GROUP).
- Run at BELOW_NORMAL process priority to leave CPU/GPU headroom for resident LLM turns.
- JSON Lines protocol over stdout with dedicated reader threads to prevent Windows pipe deadlocks.
- Bounded event bus for SSE telemetry clients (/api/jobs/stream) that never blocks producers.
- Complete process tree termination (taskkill /T /F) to prevent orphaned renders.
"""

import enum
import json
import logging
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

logger = logging.getLogger("zaine.core.job_supervisor")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    LOST = "LOST"


@dataclass
class JobRecord:
    job_id: str
    command: List[str]
    description: str
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    exit_code: Optional[int] = None
    progress: float = 0.0
    last_log: str = ""
    artifacts: List[str] = field(default_factory=list)
    pid: Optional[int] = None
    timeout_s: float = 3600.0
    last_broadcast_ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class JobSupervisor:
    _instance: Optional["JobSupervisor"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._jobs: Dict[str, JobRecord] = {}
        self._subscribers: Set[queue.Queue] = set()
        self._mutex = threading.Lock()
        self._seq = 0

    @classmethod
    def get_instance(cls) -> "JobSupervisor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def subscribe(self, max_buffer: int = 100) -> queue.Queue:
        """Subscribes an SSE client to the telemetry bus."""
        q: queue.Queue = queue.Queue(maxsize=max_buffer)
        with self._mutex:
            self._subscribers.add(q)
        logger.debug("New SSE client subscribed to job telemetry (total: %d)", len(self._subscribers))
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Removes an SSE client queue."""
        with self._mutex:
            self._subscribers.discard(q)
        logger.debug("SSE client unsubscribed from job telemetry (remaining: %d)", len(self._subscribers))

    def broadcast(self, event_type: str, job_id: str, data: Dict[str, Any]) -> None:
        """
        Broadcasts an event to all subscribers.
        Non-blocking: if a subscriber queue is full, drops the oldest event.
        """
        with self._mutex:
            self._seq += 1
            payload = {
                "v": 1,
                "seq": self._seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "job_id": job_id,
                "type": event_type,
                "data": data
            }
            dead = set()
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    # Drop oldest to prevent stalling producers
                    try:
                        q.get_nowait()
                        q.put_nowait(payload)
                    except Exception:
                        dead.add(q)
                except Exception:
                    dead.add(q)
            self._subscribers.difference_update(dead)

    def submit_job(
        self,
        command: List[str],
        description: str,
        timeout_s: float = 3600.0,
        env_extra: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Submits an Armory task as an isolated OS subprocess.
        Returns: job_id
        """
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        job = JobRecord(
            job_id=job_id,
            command=command,
            description=description,
            timeout_s=timeout_s
        )

        with self._mutex:
            self._jobs[job_id] = job

        # Spawn worker thread to oversee execution
        thread = threading.Thread(
            target=self._run_job_subprocess,
            args=(job, env_extra),
            name=f"JobSupervisor-{job_id}",
            daemon=True
        )
        thread.start()
        self.broadcast("job_queued", job_id, {"description": description})
        return job_id

    def _run_job_subprocess(self, job: JobRecord, env_extra: Optional[Dict[str, str]] = None) -> None:
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        job.status = JobStatus.STARTING
        job.started_at = time.time()
        self.broadcast("job_started", job.job_id, {"command": job.command})

        try:
            proc = subprocess.Popen(
                job.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                creationflags=creationflags
            )
            job.pid = proc.pid
            job.status = JobStatus.RUNNING

            # Set BELOW_NORMAL priority class
            if HAS_PSUTIL and job.pid:
                try:
                    p = psutil.Process(job.pid)
                    if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
                        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                except Exception:
                    pass

            # Read stdout line by line (Windows-safe pipe draining)
            if proc.stdout:
                try:
                    for raw_line in iter(proc.stdout.readline, ""):
                        line = raw_line.strip()
                        if not line:
                            continue
                        job.last_log = line
                        self._parse_and_broadcast_line(job, line)
                finally:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass

            proc.wait(timeout=job.timeout_s)
            job.exit_code = proc.returncode
            job.finished_at = time.time()

            if job.status == JobStatus.CANCELLED:
                # Retain CANCELLED state
                pass
            elif proc.returncode == 0:
                job.status = JobStatus.SUCCEEDED
                job.progress = 100.0
                self.broadcast("job_succeeded", job.job_id, {"exit_code": 0, "artifacts": job.artifacts})
            else:
                job.status = JobStatus.FAILED
                self.broadcast("job_failed", job.job_id, {"exit_code": proc.returncode, "error": job.last_log})

        except subprocess.TimeoutExpired:
            self.cancel_job(job.job_id)
            job.status = JobStatus.TIMED_OUT
            self.broadcast("job_timed_out", job.job_id, {"timeout_s": job.timeout_s})
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.finished_at = time.time()
            self.broadcast("job_failed", job.job_id, {"error": str(exc)})
            logger.error("Job execution exception: %s", exc)

    def _parse_and_broadcast_line(self, job: JobRecord, line: str) -> None:
        """Parses structured JSON Lines or regular log output."""
        now = time.time()
        # Coalesce high-frequency telemetry to max 4 Hz (every 250ms)
        throttle = (now - job.last_broadcast_ts) < 0.25

        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                evt_type = data.get("type", "log")
                if "progress" in data:
                    job.progress = float(data["progress"])
                if "artifact" in data:
                    job.artifacts.append(str(data["artifact"]))

                if evt_type == "progress" and throttle:
                    return  # skip throttled progress tick

                job.last_broadcast_ts = now
                self.broadcast(f"job_{evt_type}", job.job_id, data)
                return
            except json.JSONDecodeError:
                pass

        # Standard log output
        if not throttle:
            job.last_broadcast_ts = now
            self.broadcast("job_log", job.job_id, {"line": line[:300]})

    def cancel_job(self, job_id: str) -> bool:
        """Terminates an Armory job process tree cleanly."""
        with self._mutex:
            job = self._jobs.get(job_id)
            if not job or not job.pid:
                return False

            pid = job.pid
            job.status = JobStatus.CANCELLED
            job.finished_at = time.time()

        if os.name == "nt":
            # Windows: kill entire process tree (/T /F)
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5
                )
            except Exception as e:
                logger.warning("taskkill error on pid %s: %s", pid, e)
        else:
            if HAS_PSUTIL:
                try:
                    parent = psutil.Process(pid)
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                except Exception:
                    pass

        self.broadcast("job_cancelled", job_id, {"pid": pid})
        return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._mutex:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._mutex:
            sorted_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True
            )
            return [j.to_dict() for j in sorted_jobs[:limit]]


def get_job_supervisor() -> JobSupervisor:
    return JobSupervisor.get_instance()
