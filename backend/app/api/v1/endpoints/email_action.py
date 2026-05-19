from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.email_action import EmailMessage, EmailSyncState
from app.schemas.email_action import (
    EmailMessageOut, EmailUpdateIn, SyncResultOut, DashboardOut,
)
from app.services.gmail_service import fetch_new_emails
from app.services.email_analyzer import analyze_email, AnalysisError
from app.config import settings

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_create_state(db: Session) -> EmailSyncState:
    state = db.query(EmailSyncState).first()
    if not state:
        state = EmailSyncState()
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


# ── Sync ──────────────────────────────────────────────────────────────────────

@router.post("/sync", response_model=SyncResultOut)
def sync_emails(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail credentials not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD in .env",
        )

    state = _get_or_create_state(db)

    try:
        messages = fetch_new_emails(
            gmail_user=settings.GMAIL_USER,
            app_password=settings.GMAIL_APP_PASSWORD,
            last_uid=state.last_uid,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gmail fetch failed: {exc}",
        )

    synced = 0
    max_uid = state.last_uid or 0

    for m in messages:
        if db.query(EmailMessage).filter(EmailMessage.message_uid == m['uid']).first():
            continue

        analysis = None
        if settings.OLLAMA_URL:
            analysis = analyze_email(
                subject=m['subject'],
                body=m['body_text'],
                sender=m.get('sender', ''),
                ollama_url=settings.OLLAMA_URL,
                ollama_model=settings.OLLAMA_MODEL,
            )

        received_at = m.get('received_at')
        if received_at and received_at.tzinfo is not None:
            received_at = received_at.replace(tzinfo=None)

        a = analysis or {}
        record = EmailMessage(
            message_uid     = m['uid'],
            subject         = m['subject'],
            sender          = m['sender'],
            received_at     = received_at,
            body_text       = m['body_text'],
            category        = a.get('category'),
            priority        = a.get('priority'),
            sentiment       = a.get('sentiment'),
            ai_summary      = a.get('summary'),
            initial_summary = a.get('initial_summary'),
            project_name    = a.get('project_name'),
            zone            = a.get('zone'),
            key_points      = a.get('key_points'),
            action_items    = a.get('action_items'),
            building_name   = a.get('building_name'),
            flat_info       = a.get('flat_info'),
            occupant_type   = a.get('occupant_type'),
            event_date      = a.get('event_date'),
            reason_purpose  = a.get('reason_purpose'),
            person_name     = a.get('person_name'),
            person_contact  = a.get('person_contact'),
            contact_to      = a.get('contact_to'),
        )
        db.add(record)
        synced += 1
        max_uid = max(max_uid, m['uid'])

    if synced:
        state.last_uid     = max_uid
        state.last_sync_at = datetime.utcnow()
        db.commit()

    return SyncResultOut(
        synced   = synced,
        last_uid = state.last_uid,
        message  = f"Synced {synced} new email(s)." if synced else "No new emails.",
    )


# ── Manual AI re-analysis ─────────────────────────────────────────────────────

@router.post("/messages/{msg_id}/reanalyze", response_model=EmailMessageOut)
def reanalyze_message(
    msg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    msg = db.query(EmailMessage).filter(EmailMessage.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    if not settings.OLLAMA_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama not configured. Set OLLAMA_URL in .env",
        )

    try:
        analysis = analyze_email(
            subject=msg.subject or '',
            body=msg.body_text or '',
            sender=msg.sender or '',
            ollama_url=settings.OLLAMA_URL,
            ollama_model=settings.OLLAMA_MODEL,
        )
    except AnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    a = analysis
    msg.category        = a.get('category')       or msg.category
    msg.priority        = a.get('priority')        or msg.priority
    msg.sentiment       = a.get('sentiment')       or msg.sentiment
    msg.ai_summary      = a.get('summary')         or msg.ai_summary
    msg.initial_summary = a.get('initial_summary') or msg.initial_summary
    msg.project_name    = a.get('project_name')    or msg.project_name
    msg.zone            = a.get('zone')            or msg.zone
    msg.key_points      = a.get('key_points')      or msg.key_points
    msg.action_items    = a.get('action_items')    or msg.action_items
    msg.building_name   = a.get('building_name')   or msg.building_name
    msg.flat_info       = a.get('flat_info')       or msg.flat_info
    msg.occupant_type   = a.get('occupant_type')   or msg.occupant_type
    msg.event_date      = a.get('event_date')      or msg.event_date
    msg.reason_purpose  = a.get('reason_purpose')  or msg.reason_purpose
    msg.person_name     = a.get('person_name')
    msg.person_contact  = a.get('person_contact')
    msg.contact_to      = a.get('contact_to')
    msg.updated_at      = datetime.utcnow()

    db.commit()
    db.refresh(msg)
    return msg


# ── List / detail ─────────────────────────────────────────────────────────────

@router.get("/messages", response_model=List[EmailMessageOut])
def list_messages(
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = db.query(EmailMessage).order_by(EmailMessage.received_at.desc())
    if category:
        q = q.filter(EmailMessage.category == category)
    if priority:
        q = q.filter(EmailMessage.priority == priority)
    if status_filter:
        q = q.filter(EmailMessage.status == status_filter)
    if search:
        like = f"%{search}%"
        q = q.filter(
            EmailMessage.subject.ilike(like) |
            EmailMessage.sender.ilike(like) |
            EmailMessage.ai_summary.ilike(like)
        )
    return q.all()


@router.get("/messages/{msg_id}", response_model=EmailMessageOut)
def get_message(
    msg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    msg = db.query(EmailMessage).filter(EmailMessage.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    return msg


@router.patch("/messages/{msg_id}", response_model=EmailMessageOut)
def update_message(
    msg_id: int,
    payload: EmailUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    msg = db.query(EmailMessage).filter(EmailMessage.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    if payload.status is not None:
        msg.status = payload.status
    if payload.assigned_to is not None:
        msg.assigned_to = payload.assigned_to
    if payload.response_text is not None:
        msg.response_text = payload.response_text
        msg.response_by   = payload.response_by or current_user.username
        msg.responded_at  = datetime.utcnow()
    if payload.response_by is not None:
        msg.response_by = payload.response_by

    msg.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)
    return msg


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    all_msgs = db.query(EmailMessage).all()
    total      = len(all_msgs)
    unresolved = sum(1 for m in all_msgs if m.status not in ('resolved', 'closed'))

    by_category: dict = {}
    by_priority: dict = {}
    by_status:   dict = {}

    for m in all_msgs:
        cat  = m.category or 'other'
        pri  = m.priority or 'low'
        stat = m.status   or 'new'
        by_category[cat]  = by_category.get(cat, 0) + 1
        by_priority[pri]  = by_priority.get(pri, 0) + 1
        by_status[stat]   = by_status.get(stat, 0) + 1

    recent = (
        db.query(EmailMessage)
        .filter(EmailMessage.status.in_(['new', 'in_progress']))
        .order_by(EmailMessage.received_at.desc())
        .limit(5)
        .all()
    )

    return DashboardOut(
        total       = total,
        unresolved  = unresolved,
        by_category = by_category,
        by_priority = by_priority,
        by_status   = by_status,
        recent      = recent,
    )
