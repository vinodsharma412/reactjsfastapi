import httpx
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Phone patterns for Indian numbers and international formats
_PHONE_RE = re.compile(
    r'(?:\+?91[-.\s]?)?'          # optional India country code
    r'(?:'
        r'[6-9]\d{9}'             # 10-digit Indian mobile
        r'|'
        r'\d{3,5}[-.\s]\d{3,4}[-.\s]\d{4}'   # XXX-XXX-XXXX style
    r')',
    re.ASCII,
)

_PROMPT = """You are a business email analyst. Read the email. Reply with ONLY this JSON — fill every key, use null when unknown. No extra text.

{{
  "category": "...",
  "priority": "...",
  "sentiment": "...",
  "person_name": "...",
  "person_contact": "...",
  "contact_to": "...",
  "building_name": "...",
  "flat_info": "...",
  "reason_purpose": "...",
  "summary": "...",
  "initial_summary": "...",
  "key_points": [],
  "action_items": [],
  "occupant_type": "...",
  "event_date": "...",
  "zone": "...",
  "project_name": "..."
}}

Rules:
- category: request|issue|complaint|escalation|inquiry|sales|other  (issue = damage/defect/leak/broken; inquiry = asking a question)
- priority: fatal|critical|medium|low
- sentiment: positive|neutral|negative
- person_name: full name of sender/initiator
- person_contact: phone number from email body or signature — PHONES hint: {phones}
- contact_to: infer the team or role who should handle this (e.g. "Maintenance team", "Building Manager")
- building_name: society or building name
- flat_info: flat/unit number (e.g. A-101)
- reason_purpose: one sentence describing the core issue
- summary: one sentence overall summary
- initial_summary: one sentence about the very first email in the thread
- key_points: array of 2-3 short phrases
- action_items: array of required actions, or []
- occupant_type: owner|tenant|visitor|committee|staff
- event_date: date as text, or null
- zone: city/region, or null
- project_name: project name, or null

Subject: {subject}
From: {sender}
Email:
{body}"""


class AnalysisError(Exception):
    """Raised when Ollama analysis fails; message is user-facing."""


def _find_phones(text: str) -> str:
    """Return a comma-separated list of phone numbers found in text, or 'none found'."""
    hits = list(dict.fromkeys(                # deduplicate, preserve order
        m.strip() for m in _PHONE_RE.findall(text) if len(m.strip()) >= 7
    ))
    return ', '.join(hits) if hits else 'none found'


def _smart_truncate(body: str, limit: int = 1800) -> str:
    """Return first 2/3 + last 1/3 of body so signatures are included."""
    if len(body) <= limit:
        return body
    head = limit * 2 // 3
    tail = limit - head
    return body[:head] + '\n...\n' + body[-tail:]


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract the outermost JSON object."""
    text = raw.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else text[3:]
        text = text.rsplit('```', 1)[0].strip()
    start = text.find('{')
    end   = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def analyze_email(
    subject: str,
    body: str,
    ollama_url: str,
    ollama_model: str,
    sender: str = '',
) -> Optional[dict]:
    full_body = body or ''
    phones    = _find_phones(full_body)
    body_part = _smart_truncate(full_body)

    prompt = _PROMPT.format(
        subject=subject or '(no subject)',
        sender=sender or '(unknown)',
        phones=phones,
        body=body_part,
    )
    try:
        resp = httpx.post(
            f"{ollama_url.rstrip('/')}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": -1, "num_ctx": 4096, "temperature": 0},
            },
            timeout=120.0,
        )
    except httpx.ConnectError:
        raise AnalysisError(f"Cannot connect to Ollama at {ollama_url}. Is it running?")
    except httpx.TimeoutException:
        raise AnalysisError("Ollama request timed out (>120s). Try a smaller email body.")

    if resp.status_code != 200:
        try:
            detail = resp.json().get('error', resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise AnalysisError(f"Ollama returned {resp.status_code}: {detail}")

    raw = resp.json().get('response', '').strip()
    if not raw:
        raise AnalysisError("Ollama returned an empty response.")

    try:
        result = _extract_json(raw)
    except json.JSONDecodeError:
        logger.warning("Ollama non-JSON response: %s", raw[:300])
        raise AnalysisError(f"Ollama response was not valid JSON. Raw: {raw[:200]}")

    # If model still returned null for person_contact but we found phones, fill it in
    if not result.get('person_contact') and phones != 'none found':
        result['person_contact'] = phones.split(',')[0].strip()

    logger.info("Ollama analysis OK — model=%s phones=%s", ollama_model, phones)
    return result
