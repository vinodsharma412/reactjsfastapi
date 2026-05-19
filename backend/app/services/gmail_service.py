import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def _decode_str(value) -> str:
    if not value:
        return ''
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(str(part))
    return ' '.join(result).strip()


def _get_body(msg) -> str:
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            ct   = part.get_content_type()
            disp = str(part.get('Content-Disposition', ''))
            if ct == 'text/plain' and 'attachment' not in disp:
                charset = part.get_content_charset() or 'utf-8'
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors='replace')
                break
    else:
        charset = msg.get_content_charset() or 'utf-8'
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(charset, errors='replace')
    return body.strip()


def fetch_new_emails(gmail_user: str, app_password: str, last_uid: Optional[int] = None) -> List[dict]:
    imap = imaplib.IMAP4_SSL('imap.gmail.com')
    imap.login(gmail_user, app_password)
    imap.select('INBOX')

    if last_uid:
        typ, data = imap.uid('SEARCH', None, f'UID {last_uid + 1}:*')
    else:
        typ, data = imap.uid('SEARCH', None, 'ALL')

    uid_list = data[0].split() if data[0] else []

    if not last_uid:
        uid_list = uid_list[-50:]  # initial sync: most recent 50 only

    messages = []
    for uid_bytes in uid_list:
        uid = int(uid_bytes)
        if last_uid and uid <= last_uid:
            continue

        typ, msg_data = imap.uid('FETCH', str(uid), '(RFC822)')
        if not msg_data or not msg_data[0]:
            continue

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = _decode_str(msg.get('Subject', ''))
        sender  = _decode_str(msg.get('From', ''))
        body    = _get_body(msg)

        received_at = None
        date_str = msg.get('Date')
        if date_str:
            try:
                received_at = parsedate_to_datetime(date_str)
            except Exception:
                pass

        messages.append({
            'uid':         uid,
            'subject':     subject,
            'sender':      sender,
            'received_at': received_at,
            'body_text':   body,
        })

    imap.logout()
    return messages
