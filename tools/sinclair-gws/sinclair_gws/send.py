"""send_draft: the only way anything leaves. Promotes an existing Gmail draft by id.

Two properties, both enforced by Gmail itself rather than by state we keep:
- The approved bytes are the sent bytes: users.drafts.send transmits the draft as
  reviewed. There is no compose-at-send path anywhere in this package.
- A draft id is sent at most once: Gmail deletes the draft on a successful send, so a
  second send of the same id is a 404 from Google. The Sent folder is the audit trail.
An in-process lock serialises concurrent calls; nothing is written to disk.
"""
from __future__ import annotations

import threading

from . import config
from .google import Google, GoogleError


class DraftNotFound(LookupError):
    pass


_lock = threading.Lock()


def locate_draft(g: Google, draft_id: str) -> str:
    for alias in config.IDENTITIES:
        try:
            g.gmail_get_draft(alias, draft_id)
            return alias
        except GoogleError as e:
            if e.status in (400, 404):
                continue
            raise
    raise DraftNotFound(
        f"draft {draft_id} is not in any mailbox this server holds: it never existed or it was "
        "already sent. If it was sent, the message id returned at draft time is in the Sent folder."
    )


def send_draft(g: Google, draft_id: str) -> dict:
    with _lock:
        holder = locate_draft(g, draft_id)
        try:
            sent = g.gmail_send_draft(holder, draft_id)
        except GoogleError as e:
            if e.status == 404:
                raise DraftNotFound(f"draft {draft_id} vanished before send; it was most likely sent concurrently") from None
            raise
        return {
            "draft_id": draft_id,
            "as": holder,
            "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
        }
