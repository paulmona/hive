"""Thin authenticated HTTP to the Gmail and Calendar REST APIs.

httpx directly, no discovery client: the surface this server needs is a dozen
endpoints and a discovery document is one more thing to cache and get wrong.
"""
from __future__ import annotations

from typing import Any

import httpx

from .auth import TokenSource

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3"


class GoogleError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Google API {status}: {body[:300]}")
        self.status = status


class Google:
    def __init__(self, tokens: TokenSource | None = None, timeout: float = 30.0):
        self._tokens = tokens or TokenSource()
        self._http = httpx.Client(timeout=timeout)

    def request(self, alias: str, method: str, url: str, **kw: Any) -> Any:
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._tokens.token(alias)}"
        r = self._http.request(method, url, headers=headers, **kw)
        if r.status_code >= 400:
            raise GoogleError(r.status_code, r.text)
        return r.json() if r.content else None

    # Gmail
    def gmail_profile(self, alias: str) -> dict:
        return self.request(alias, "GET", f"{GMAIL}/profile")

    def gmail_create_draft(self, alias: str, raw_b64: str, thread_id: str | None) -> dict:
        message: dict = {"raw": raw_b64}
        if thread_id:
            message["threadId"] = thread_id
        return self.request(alias, "POST", f"{GMAIL}/drafts", json={"message": message})

    def gmail_get_draft(self, alias: str, draft_id: str) -> dict:
        return self.request(alias, "GET", f"{GMAIL}/drafts/{draft_id}", params={"format": "metadata"})

    def gmail_delete_draft(self, alias: str, draft_id: str) -> None:
        self.request(alias, "DELETE", f"{GMAIL}/drafts/{draft_id}")

    def gmail_send_draft(self, alias: str, draft_id: str) -> dict:
        # users.drafts.send: the reviewed bytes go out unchanged. This is the only
        # send call in the server; a test greps the source to keep it that way.
        return self.request(alias, "POST", f"{GMAIL}/drafts/send", json={"id": draft_id})
