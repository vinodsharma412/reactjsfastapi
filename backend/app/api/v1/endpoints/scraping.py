"""Amazon ASIN scraping job endpoints + SSE event streams.

REST endpoints:
    POST   /jobs          — create a new scraping job
    GET    /jobs          — list jobs (ADMIN/MANAGER see all; VIEWER sees own)
    GET    /jobs/{id}     — get a single job with task detail

SSE streams (``text/event-stream``):
    GET    /events            — live job list, updates on any state change
    GET    /jobs/{id}/events  — live single-job detail, closes when done
"""

import asyncio
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal, get_db
from app.dependencies import get_current_active_user
from app.models.scraping import ScrapingJob, ScrapingTask
from app.models.user import User
from app.schemas.scraping import JobCreate, JobOut
from app.services.scraping_queue import enqueue

#: SSE poll interval (seconds) while tasks are actively running/pending.
_SSE_ACTIVE_INTERVAL = 1

#: SSE poll interval (seconds) when no tasks are in-flight (save CPU).
_SSE_IDLE_INTERVAL = 5

router = APIRouter()


# ── Serialisation helpers ──────────────────────────────────────────────────────


def _task_to_dict(t: ScrapingTask) -> dict:
    """Serialise a ``ScrapingTask`` (+ optional joined ``ProductData``) to a dict.

    Args:
        t: ORM task object, optionally with ``t.product`` loaded.

    Returns:
        A plain dict suitable for JSON serialisation.
    """
    product = None
    if t.product:
        p = t.product
        product = {
            "asin": p.asin,
            "title": p.title,
            "brand": p.brand,
            "price": p.price,
            "rating": p.rating,
            "review_count": p.review_count,
            "availability": p.availability,
            "image_url": p.image_url,
            "scraped_at": str(p.scraped_at) if p.scraped_at else None,
        }
    return {
        "id": t.id,
        "asin": t.asin,
        "status": t.status,
        "error": t.error,
        "queued_at": str(t.queued_at) if t.queued_at else None,
        "started_at": str(t.started_at) if t.started_at else None,
        "completed_at": str(t.completed_at) if t.completed_at else None,
        "product": product,
    }


def _job_to_dict(job: ScrapingJob, include_tasks: bool = False) -> dict:
    """Serialise a ``ScrapingJob`` to a dict.

    Task counters are derived from the actual task rows when they are loaded
    (``include_tasks=True``) to protect against counter drift caused by mid-
    flight crashes.

    Args:
        job: ORM job object, optionally with ``job.tasks`` and ``job.user`` loaded.
        include_tasks: When ``True``, include the full task list in the output.

    Returns:
        A plain dict suitable for JSON serialisation.
    """
    tasks = job.tasks if job.tasks is not None else []
    if tasks:
        pending = sum(1 for t in tasks if t.status == "pending")
        running = sum(1 for t in tasks if t.status == "running")
        completed = sum(1 for t in tasks if t.status == "completed")
        failed = sum(1 for t in tasks if t.status == "failed")
    else:
        pending, running, completed, failed = (
            job.pending,
            job.running,
            job.completed,
            job.failed,
        )
    return {
        "id": job.id,
        "user_id": job.user_id,
        "username": job.user.username if job.user else None,
        "total": job.total,
        "pending": pending,
        "running": running,
        "completed": completed,
        "failed": failed,
        "created_at": str(job.created_at) if job.created_at else None,
        "tasks": [_task_to_dict(t) for t in tasks] if include_tasks else None,
    }


# ── REST endpoints ─────────────────────────────────────────────────────────────


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Create a new scraping job and enqueue all ASINs.

    Atomically creates the ``ScrapingJob`` and one ``ScrapingTask`` per ASIN,
    then puts each task ID onto the in-process queue so the background worker
    picks them up immediately.

    Args:
        payload: ``JobCreate`` body containing the list of ASIN strings.
        db: Database session.
        current_user: The user creating the job (stored as ``job.user_id``).

    Returns:
        The created job serialised as ``JobOut``, including the full task list.
    """
    asins = payload.asins

    job = ScrapingJob(user_id=current_user.id, total=len(asins), pending=len(asins))
    db.add(job)
    db.commit()
    db.refresh(job)

    tasks = []
    for asin in asins:
        t = ScrapingTask(job_id=job.id, asin=asin, status="pending")
        db.add(t)
        tasks.append(t)
    db.commit()

    for t in tasks:
        db.refresh(t)
        enqueue(t.id)

    job = (
        db.query(ScrapingJob)
        .options(joinedload(ScrapingJob.user), joinedload(ScrapingJob.tasks))
        .filter(ScrapingJob.id == job.id)
        .first()
    )
    return _job_to_dict(job, include_tasks=True)


@router.get("/jobs", response_model=List[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """List scraping jobs visible to the current user.

    ADMIN and MANAGER see all jobs; VIEWER sees only their own.

    Args:
        db: Database session.
        current_user: Authenticated user determining the visibility scope.

    Returns:
        A list of jobs serialised as ``JobOut`` (without task detail).
    """
    query = (
        db.query(ScrapingJob)
        .options(joinedload(ScrapingJob.user), joinedload(ScrapingJob.tasks))
        .order_by(ScrapingJob.created_at.desc())
    )
    if current_user.role == "viewer":
        query = query.filter(ScrapingJob.user_id == current_user.id)
    return [_job_to_dict(j) for j in query.all()]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Retrieve a single scraping job with full task detail.

    Args:
        job_id: Primary key of the ``ScrapingJob``.
        db: Database session.
        current_user: Used for ownership check when role is VIEWER.

    Returns:
        The job serialised as ``JobOut`` including all tasks and product data.

    Raises:
        HTTPException 404: If the job does not exist.
        HTTPException 403: If a VIEWER requests a job they don't own.
    """
    job = (
        db.query(ScrapingJob)
        .options(
            joinedload(ScrapingJob.user),
            joinedload(ScrapingJob.tasks).joinedload(ScrapingTask.product),
        )
        .filter(ScrapingJob.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if current_user.role == "viewer" and job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return _job_to_dict(job, include_tasks=True)


# ── SSE streams ────────────────────────────────────────────────────────────────


@router.get("/events")
async def jobs_event_stream(
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """SSE stream emitting the full job list whenever state changes.

    Polls the database every ``_SSE_ACTIVE_INTERVAL`` seconds while any job
    has pending/running tasks, and every ``_SSE_IDLE_INTERVAL`` seconds when
    idle.  Only sends a frame when the payload differs from the last send.

    Args:
        current_user: Used to scope visibility (VIEWER sees own jobs only).

    Returns:
        A ``StreamingResponse`` with ``Content-Type: text/event-stream``.
    """
    user_id = current_user.id
    user_role = current_user.role

    def fetch() -> str:
        db = SessionLocal()
        try:
            query = (
                db.query(ScrapingJob)
                .options(joinedload(ScrapingJob.user), joinedload(ScrapingJob.tasks))
                .order_by(ScrapingJob.created_at.desc())
            )
            if user_role == "viewer":
                query = query.filter(ScrapingJob.user_id == user_id)
            jobs = query.all()
            return json.dumps([_job_to_dict(j) for j in jobs])
        finally:
            db.close()

    async def generate():
        last = None
        while True:
            try:
                payload = await asyncio.to_thread(fetch)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(2)
                continue

            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload

            has_active = any(
                j.get("pending", 0) > 0 or j.get("running", 0) > 0
                for j in json.loads(payload)
            )
            await asyncio.sleep(
                _SSE_ACTIVE_INTERVAL if has_active else _SSE_IDLE_INTERVAL
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}/events")
async def job_event_stream(
    job_id: int,
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """SSE stream for a single job — closes automatically when all tasks finish.

    Polls every ``_SSE_ACTIVE_INTERVAL`` seconds and sends the current job
    state only when it differs from the previous frame.  The generator exits
    (closing the stream) once ``pending == 0`` and ``running == 0``.

    Args:
        job_id: Primary key of the job to stream.
        current_user: Used for VIEWER ownership enforcement.

    Returns:
        A ``StreamingResponse`` with ``Content-Type: text/event-stream``.
    """
    user_id = current_user.id
    user_role = current_user.role

    def fetch():
        db = SessionLocal()
        try:
            job = (
                db.query(ScrapingJob)
                .options(
                    joinedload(ScrapingJob.user),
                    joinedload(ScrapingJob.tasks).joinedload(ScrapingTask.product),
                )
                .filter(ScrapingJob.id == job_id)
                .first()
            )
            if not job:
                return None, False
            if user_role == "viewer" and job.user_id != user_id:
                return None, False
            data = _job_to_dict(job, include_tasks=True)
            done = data["pending"] == 0 and data["running"] == 0
            return json.dumps(data), done
        finally:
            db.close()

    async def generate():
        last = None
        while True:
            try:
                payload, done = await asyncio.to_thread(fetch)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(1)
                continue

            if payload is None:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                break

            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload

            if done:
                break

            await asyncio.sleep(_SSE_ACTIVE_INTERVAL)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
