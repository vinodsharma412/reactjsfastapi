from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from app.db.base import Base


class EmailSyncState(Base):
    __tablename__ = "email_sync_state"

    id           = Column(Integer, primary_key=True, index=True)
    last_uid     = Column(Integer, nullable=True)    # IMAP UID of last synced message
    last_sync_at = Column(DateTime, nullable=True)


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id          = Column(Integer, primary_key=True, index=True)
    message_uid = Column(Integer, nullable=False, unique=True)  # IMAP UID
    subject     = Column(Text, nullable=True)
    sender      = Column(String(500), nullable=True)
    received_at = Column(DateTime, nullable=True)
    body_text   = Column(Text, nullable=True)

    # AI analysis — general
    category     = Column(String(50), nullable=True)
    priority     = Column(String(20), nullable=True)
    sentiment    = Column(String(20), nullable=True)
    ai_summary   = Column(Text, nullable=True)
    project_name = Column(String(255), nullable=True)
    zone         = Column(String(100), nullable=True)
    key_points   = Column(JSON, nullable=True)
    action_items = Column(JSON, nullable=True)

    # AI analysis — structured smart summary
    building_name  = Column(String(255), nullable=True)
    flat_info      = Column(String(255), nullable=True)
    occupant_type  = Column(String(50),  nullable=True)
    event_date     = Column(String(100), nullable=True)
    reason_purpose = Column(Text, nullable=True)

    # AI analysis — person / contact details
    person_name    = Column(String(300), nullable=True)
    person_contact = Column(String(100), nullable=True)
    contact_to     = Column(String(300), nullable=True)
    initial_summary = Column(Text,         nullable=True)

    # Response tracking
    status        = Column(String(30), nullable=False, default="new")  # new, in_progress, resolved, closed
    assigned_to   = Column(String(255), nullable=True)
    response_text = Column(Text, nullable=True)
    response_by   = Column(String(255), nullable=True)
    responded_at  = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
