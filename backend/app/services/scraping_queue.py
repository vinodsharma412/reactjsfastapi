"""Background scraping queue — thread-based, no asyncio.

Uses ``queue.Queue`` (thread-safe) so it works correctly under
``uvicorn --reload`` and debugpy without blocking the async event loop.

At most ``MAX_CONCURRENT`` ASIN scraping tasks run simultaneously; the rest
wait in the queue.  On server startup, ``start_worker()`` re-enqueues any
tasks that were interrupted mid-flight by a previous process crash.
"""

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

#: Maximum number of ASIN scrapes that may run concurrently.
MAX_CONCURRENT: int = 2

_task_queue: queue.Queue = queue.Queue()
_semaphore: threading.Semaphore = threading.Semaphore(MAX_CONCURRENT)

# +1 worker slot: one thread dispatches from the queue; the rest do the work.
_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT + 1, thread_name_prefix="scraper"
)
_worker_thread: Optional[threading.Thread] = None


# ── Public API ─────────────────────────────────────────────────────────────────


def enqueue(task_id: int) -> None:
    """Put a scraping task ID onto the work queue.

    Thread-safe — may be called from any thread or an async context.

    Args:
        task_id: Primary key of the ``ScrapingTask`` row to process.
    """
    _task_queue.put(task_id)


def start_worker() -> None:
    """Start the background dispatcher thread.

    Should be called exactly once from the application lifespan startup hook.
    Calls ``_recover_pending`` first so that tasks interrupted by a previous
    server crash are automatically re-queued.
    """
    global _worker_thread
    _recover_pending()
    _worker_thread = threading.Thread(
        target=_worker_loop, daemon=True, name="scraping-worker"
    )
    _worker_thread.start()
    logger.info("Scraping worker started (max_concurrent=%d)", MAX_CONCURRENT)


# ── Internal ───────────────────────────────────────────────────────────────────


def _worker_loop() -> None:
    """Dispatcher loop running in a daemon thread.

    Blocks on the queue indefinitely and submits each task ID to the thread
    pool, where it waits for a semaphore slot before executing.
    """
    while True:
        task_id = _task_queue.get()
        _executor.submit(_process_with_semaphore, task_id)


def _process_with_semaphore(task_id: int) -> None:
    """Acquire a semaphore slot then process *task_id*.

    The semaphore limits concurrency to ``MAX_CONCURRENT`` active scrapes.

    Args:
        task_id: Primary key of the ``ScrapingTask`` row to process.
    """
    with _semaphore:
        _process_sync(task_id)


def _process_sync(task_id: int) -> None:
    """Fetch, scrape, and persist results for one ASIN.

    Runs inside a thread-pool thread.  Opens its own DB session and closes it
    in the ``finally`` block to prevent connection leaks.

    Lifecycle:
        1. Mark task ``running``, decrement job ``pending``, increment ``running``.
        2. Call ``scrape_amazon_asin`` and persist a ``ProductData`` row.
        3. On success: mark ``completed``, update counters.
        4. On failure: mark ``failed``, store truncated error message.

    Args:
        task_id: Primary key of the ``ScrapingTask`` row to process.
    """
    from app.db.session import SessionLocal
    from app.models.scraping import ProductData, ScrapingJob, ScrapingTask
    from app.services.scraper import scrape_amazon_asin

    db = SessionLocal()
    try:
        task = db.query(ScrapingTask).filter(ScrapingTask.id == task_id).first()
        if not task or task.status != "pending":
            return  # already processed or duplicate enqueue

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

        except Exception as exc:  # noqa: BLE001 — any scraper error must be caught
            logger.error("Task %d (ASIN %s) failed: %s", task_id, task.asin, exc)
            task.status = "failed"
            task.error = str(exc)[:500]
            task.completed_at = datetime.utcnow()
            if job:
                job.running = max(0, job.running - 1)
                job.failed += 1

        db.commit()

    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in _process_sync for task %d: %s", task_id, exc)
    finally:
        db.close()


def _recover_pending() -> None:
    """Reset interrupted tasks and re-enqueue all pending ones on startup.

    Tasks whose status was ``"running"`` when the previous process died are
    reset to ``"pending"`` so they are retried.  All pending tasks are then
    pushed onto ``_task_queue``.
    """
    from app.db.session import SessionLocal
    from app.models.scraping import ScrapingJob, ScrapingTask

    db = SessionLocal()
    try:
        interrupted = (
            db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
        )
        for t in interrupted:
            t.status = "pending"
            t.started_at = None
            job = db.query(ScrapingJob).filter(ScrapingJob.id == t.job_id).first()
            if job:
                job.running = max(0, job.running - 1)
                job.pending += 1
        if interrupted:
            db.commit()
            logger.info("Reset %d interrupted tasks to pending", len(interrupted))

        pending = db.query(ScrapingTask).filter(ScrapingTask.status == "pending").all()
        for t in pending:
            _task_queue.put(t.id)
        if pending:
            logger.info("Recovered %d pending tasks into queue", len(pending))

    except Exception as exc:  # noqa: BLE001
        logger.error("Error during recovery: %s", exc)
    finally:
        db.close()
