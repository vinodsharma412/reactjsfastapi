"""
Standalone scraping worker — runs as a separate OS process.
Polls the DB every 2 s for pending tasks and processes them.
Max 2 concurrent scrapes via threading.Semaphore.
Start automatically via FastAPI lifespan; can also be run manually.
"""
import atexit
import logging
import os
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# ── Bootstrap path so we can import app.* ─────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

import app.models.user      # noqa — must register User mapper first
import app.models.scraping  # noqa — then scraping models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scraping-worker")

PID_FILE = BACKEND_DIR / "worker.pid"

# ── Config ────────────────────────────────────────────────────────────────────
MAX_CONCURRENT = 2
POLL_INTERVAL  = 2
_semaphore     = threading.Semaphore(MAX_CONCURRENT)
_executor      = ThreadPoolExecutor(max_workers=MAX_CONCURRENT + 1)
_in_progress   : set = set()
_lock          = threading.Lock()
_stop          = threading.Event()


# ── PID guard — one instance only ────────────────────────────────────────────

def _acquire_singleton() -> bool:
    """Return False and exit early if another worker process is already alive."""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)   # signal 0 = existence check only
            logger.warning("Worker already running (PID=%d). Exiting.", old_pid)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass  # stale PID file — previous worker died

    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))
    return True


# ── Task processor ────────────────────────────────────────────────────────────

def _process_task(task_id: int) -> None:
    from app.db.session import SessionLocal
    from app.models.scraping import ScrapingTask, ScrapingJob, ProductData
    from app.services.scraper import scrape_amazon_asin

    db = SessionLocal()
    try:
        task = db.query(ScrapingTask).filter(ScrapingTask.id == task_id).first()
        if not task or task.status != "pending":
            return

        job = db.query(ScrapingJob).filter(ScrapingJob.id == task.job_id).first()

        task.status = "running"
        task.started_at = datetime.utcnow()
        if job:
            job.pending = max(0, job.pending - 1)
            job.running += 1
        db.commit()

        try:
            data = scrape_amazon_asin(task.asin)
            db.add(ProductData(task_id=task_id, **data))
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            if job:
                job.running = max(0, job.running - 1)
                job.completed += 1
            logger.info("DONE  task=%d asin=%s title=%s",
                        task_id, task.asin, (data.get("title") or "")[:60])

        except Exception as exc:
            logger.error("FAIL  task=%d asin=%s error=%s", task_id, task.asin, exc)
            task.status = "failed"
            task.error = str(exc)[:500]
            task.completed_at = datetime.utcnow()
            if job:
                job.running = max(0, job.running - 1)
                job.failed += 1

        db.commit()

    except Exception as exc:
        logger.error("DB error task=%d: %s", task_id, exc)
    finally:
        db.close()
        with _lock:
            _in_progress.discard(task_id)


def _run_with_semaphore(task_id: int) -> None:
    with _semaphore:
        _process_task(task_id)


# ── Poll loop ─────────────────────────────────────────────────────────────────

def _poll_loop() -> None:
    from app.db.session import SessionLocal
    from app.models.scraping import ScrapingTask

    logger.info("Poll loop started (max_concurrent=%d, interval=%ds)",
                MAX_CONCURRENT, POLL_INTERVAL)

    while not _stop.is_set():
        try:
            db = SessionLocal()
            pending = (
                db.query(ScrapingTask)
                .filter(ScrapingTask.status == "pending")
                .order_by(ScrapingTask.id)
                .all()
            )
            db.close()

            for task in pending:
                with _lock:
                    if task.id in _in_progress:
                        continue
                    if len(_in_progress) >= MAX_CONCURRENT:
                        break
                    _in_progress.add(task.id)
                _executor.submit(_run_with_semaphore, task.id)

        except Exception as exc:
            logger.error("Poll error: %s", exc)

        _stop.wait(POLL_INTERVAL)

    logger.info("Poll loop stopped.")


# ── Startup recovery ──────────────────────────────────────────────────────────

def _recover() -> None:
    from app.db.session import SessionLocal
    from app.models.scraping import ScrapingTask, ScrapingJob

    db = SessionLocal()
    try:
        stuck = db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
        for t in stuck:
            t.status = "pending"
            t.started_at = None
            job = db.query(ScrapingJob).filter(ScrapingJob.id == t.job_id).first()
            if job:
                job.running = max(0, job.running - 1)
                job.pending += 1
        if stuck:
            db.commit()
            logger.info("Reset %d stuck tasks to pending", len(stuck))
    finally:
        db.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT,  lambda *_: _stop.set())

    if not _acquire_singleton():
        sys.exit(0)

    logger.info("Scraping worker PID=%d starting", os.getpid())
    _recover()
    _poll_loop()
    logger.info("Scraping worker PID=%d exiting", os.getpid())


if __name__ == "__main__":
    main()
