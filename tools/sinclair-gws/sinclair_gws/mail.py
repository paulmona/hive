"""Gmail read side: search, fetch, and the holding-mailbox lookup every write tool needs.

The lookup is the important part. A message id is only meaningful inside one mailbox,
so `locate()` asks each identity's mailbox in turn and returns the one that has it.
That answer, not an argument, is what decides which identity a reply goes out as.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any

from . import config
from .google import GMAIL, Google, GoogleError


class NotFound(LookupError):
    pass


@dataclass
class Message:
    id: str
    thread_id: str
    holder: str  # identity alias whose mailbox holds this message
    headers: dict[str, str]
    body: str
    label_ids: list[str] = field(default_factory=list)
    snippet: str = ""

    def as_dict(self) -> dict[str, Any]:
        h = self.headers
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "holder": self.holder,
            "from": h.get("from", ""),
            "to": h.get("to", ""),
            "cc": h.get("cc", ""),
            "subject": h.get("subject", ""),
            "date": h.get("date", ""),
            "message_id_header": h.get("message-id", ""),
            "references": h.get("references", ""),
            "labels": self.label_ids,
            "body": self.body,
        }


# ---- MIME ---------------------------------------------------------------------

def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|tr|li|h[1-6]|blockquote)[^>]*>", re.I)
_STYLE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.I | re.S)


def html_to_text(html: str) -> str:
    text = _STYLE.sub("", html)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub("", text)
    text = unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_body(payload: dict) -> str:
    """Prefer text/plain; fall back to text/html stripped; walk multiparts depth-first."""
    plain: list[str] = []
    html: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if mime == "text/plain" and data:
            plain.append(_b64(data))
        elif mime == "text/html" and data:
            html.append(_b64(data))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    if html:
        return html_to_text("\n".join(html))
    return ""


def parse_headers(payload: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", []) if "name" in h}


def to_message(raw: dict, holder: str) -> Message:
    payload = raw.get("payload", {})
    return Message(
        id=raw["id"],
        thread_id=raw.get("threadId", ""),
        holder=holder,
        headers=parse_headers(payload),
        body=extract_body(payload),
        label_ids=raw.get("labelIds", []) or [],
        snippet=raw.get("snippet", ""),
    )


# ---- API ----------------------------------------------------------------------

_META_HEADERS = ("From", "To", "Cc", "Subject", "Date", "Message-ID", "References", "In-Reply-To")


def locate(g: Google, message_id: str) -> str:
    """Which identity's mailbox holds this id. Raises NotFound if neither."""
    for alias in config.IDENTITIES:
        try:
            g.request(alias, "GET", f"{GMAIL}/messages/{message_id}", params={"format": "minimal"})
            return alias
        except GoogleError as e:
            if e.status in (400, 404):
                continue
            raise
    raise NotFound(f"message {message_id} is not in any mailbox this server holds")


def get(g: Google, message_id: str, holder: str | None = None) -> Message:
    holder = holder or locate(g, message_id)
    raw = g.request(holder, "GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})
    return to_message(raw, holder)


def search(g: Google, mailbox: str, query: str, max_results: int = 20) -> list[dict[str, Any]]:
    config.identity(mailbox)  # refuse unknown mailboxes before any call
    max_results = max(1, min(int(max_results), 100))
    listing = g.request(mailbox, "GET", f"{GMAIL}/messages", params={"q": query, "maxResults": max_results})
    hits = []
    for ref in listing.get("messages", []) or []:
        raw = g.request(
            mailbox, "GET", f"{GMAIL}/messages/{ref['id']}",
            params=[("format", "metadata")] + [("metadataHeaders", h) for h in _META_HEADERS],
        )
        h = parse_headers(raw.get("payload", {}))
        hits.append({
            "id": raw["id"],
            "thread_id": raw.get("threadId", ""),
            "holder": mailbox,
            "from": h.get("from", ""),
            "to": h.get("to", ""),
            "subject": h.get("subject", ""),
            "date": h.get("date", ""),
            "snippet": raw.get("snippet", ""),
            "labels": raw.get("labelIds", []) or [],
        })
    return hits
