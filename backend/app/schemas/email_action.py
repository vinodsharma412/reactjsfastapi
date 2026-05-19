from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel


class EmailMessageOut(BaseModel):
    id:           int
    message_uid:  int
    subject:      Optional[str]
    sender:       Optional[str]
    received_at:  Optional[datetime]

    category:     Optional[str]
    priority:     Optional[str]
    sentiment:    Optional[str]
    ai_summary:   Optional[str]
    project_name: Optional[str]
    zone:         Optional[str]
    key_points:   Optional[List[Any]]
    action_items: Optional[List[Any]]

    building_name:  Optional[str]
    flat_info:      Optional[str]
    occupant_type:  Optional[str]
    event_date:     Optional[str]
    reason_purpose: Optional[str]

    person_name:     Optional[str]
    person_contact:  Optional[str]
    contact_to:      Optional[str]
    initial_summary: Optional[str]

    status:        str
    assigned_to:   Optional[str]
    response_text: Optional[str]
    response_by:   Optional[str]
    responded_at:  Optional[datetime]

    body_text:  Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class EmailUpdateIn(BaseModel):
    status:        Optional[str]   = None
    assigned_to:   Optional[str]   = None
    response_text: Optional[str]   = None
    response_by:   Optional[str]   = None


class SyncResultOut(BaseModel):
    synced:   int
    last_uid: Optional[int]
    message:  str


class DashboardOut(BaseModel):
    total:      int
    unresolved: int
    by_category: dict
    by_priority: dict
    by_status:   dict
    recent:      List[EmailMessageOut]
