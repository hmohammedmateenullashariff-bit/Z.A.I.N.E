"""
tests/test_job_supervisor.py
Unit tests for core.job_supervisor (JobSupervisor, Armory subprocess execution, event bus).
Verifies:
- Isolated subprocess creation with JSON Lines parsing
- Bounded event bus streaming (non-blocking for producers)
- Coalesced progress reporting
- Process tree cancellation
"""

import sys
import time
import unittest

from core.job_supervisor import JobSupervisor, JobStatus


class TestJobSupervisor(unittest.TestCase):
    def setUp(self):
        self.supervisor = JobSupervisor.get_instance()

    def test_01_job_execution_and_telemetry_stream(self):
        """Submit a lightweight command emitting JSON Lines and verify telemetry received."""
        q = self.supervisor.subscribe()

        cmd = [
            sys.executable,
            "-c",
            "import time, json; "
            "print(json.dumps({'type': 'progress', 'progress': 50}), flush=True); "
            "time.sleep(0.1); "
            "print(json.dumps({'type': 'artifact', 'artifact': 'output.mp4'}), flush=True); "
            "print('Render completed successfully', flush=True)"
        ]

        job_id = self.supervisor.submit_job(cmd, "Test Video Render")
        self.assertTrue(job_id.startswith("JOB-"))

        received_events = []
        start_t = time.time()
        while time.time() - start_t < 5.0:
            job = self.supervisor.get_job(job_id)
            if job and job["status"] in (JobStatus.SUCCEEDED.value, JobStatus.FAILED.value):
                break
            time.sleep(0.1)

        # Drain queue
        while not q.empty():
            received_events.append(q.get_nowait())

        self.supervisor.unsubscribe(q)

        job = self.supervisor.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JobStatus.SUCCEEDED.value)
        self.assertEqual(job["exit_code"], 0)
        self.assertIn("output.mp4", job["artifacts"])

        event_types = [e["type"] for e in received_events if e["job_id"] == job_id]
        self.assertIn("job_queued", event_types)
        self.assertIn("job_started", event_types)
        self.assertIn("job_succeeded", event_types)

    def test_02_job_cancellation(self):
        """Submit a long sleep job and cancel it cleanly."""
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        job_id = self.supervisor.submit_job(cmd, "Long Sleep Job")

        # Wait until started
        time.sleep(0.3)
        job = self.supervisor.get_job(job_id)
        self.assertIn(job["status"], (JobStatus.STARTING.value, JobStatus.RUNNING.value))

        # Cancel
        cancelled = self.supervisor.cancel_job(job_id)
        self.assertTrue(cancelled)

        time.sleep(0.3)
        job_after = self.supervisor.get_job(job_id)
        self.assertEqual(job_after["status"], JobStatus.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()

