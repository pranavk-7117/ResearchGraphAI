"""
Background Worker Process for ResearchGraphAI.

Runs continuous polling loop with PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED.
Handles durable background jobs, heartbeats, and graceful shutdowns.
Usage:
    python -m app.worker
"""

import os
import signal
import sys
import time
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

from app.database import SessionLocal
from app.services.jobs import JobService

RUNNING = True


def handle_shutdown(signum, frame):
    global RUNNING
    print(f"\n[Worker] Received signal {signum}. Shutting down worker loop gracefully...")
    RUNNING = False


def main():
    global RUNNING
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    print(f"[Worker] Started ResearchGraphAI background worker (ID: {worker_id}).")
    print("[Worker] Listening for pending research jobs in Supabase PostgreSQL...")

    poll_interval = 2.0

    while RUNNING:
        try:
            db = SessionLocal()
            try:
                job = JobService.acquire_next_job(db, worker_id=worker_id)
            finally:
                db.close()

            if job:
                print(f"[Worker] Acquired job {job.id} (type: {job.type}, project_id: {job.project_id}). Executing...")
                JobService.execute_job(job.id)
                print(f"[Worker] Finished execution for job {job.id}.")
            else:
                time.sleep(poll_interval)
        except Exception as e:
            print(f"[Worker] Error in worker loop: {e}")
            time.sleep(poll_interval * 2)

    print("[Worker] Worker exited cleanly.")


if __name__ == "__main__":
    main()
