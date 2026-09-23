"""Railway production entry point for CIVIL CAREER."""

import threading
import time

from app import app, create_database
from job_sync import sync_official_jobs


create_database()


def _official_job_sync_loop():
    # Give Gunicorn time to start before the first network sync.
    time.sleep(10)

    while True:
        try:
            result = sync_official_jobs()
            print("[JOB SYNC]", result, flush=True)
        except Exception as exc:
            print(
                f"[JOB SYNC ERROR] {type(exc).__name__}: {exc}",
                flush=True,
            )

        # Re-check official sources every 6 hours.
        time.sleep(6 * 60 * 60)


threading.Thread(
    target=_official_job_sync_loop,
    name="official-job-sync",
    daemon=True,
).start()
