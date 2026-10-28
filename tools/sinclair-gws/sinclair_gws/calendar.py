"""Calendar: freebusy, agenda, create/update/delete events, Meet on insert.

Same two-identity constraint as mail: `as` is an alias from the identity map or the
call is refused before any request. Mutations are limited to events the acting
identity organises, so Sinclair cannot delete or rewrite a meeting Paul owns.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config
from .google import CALENDAR, Google

DEFAULT_TZ = "America/Toronto"
HOLD_PREFIX = "HOLD: "


class NotOrganizer(PermissionError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slim(ev: dict) -> dict[str, Any]:
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary", ""),
        "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
        "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
        "status": ev.get("status"),
        "organizer": (ev.get("organizer") or {}).get("email"),
        "attendees": [a.get("email") for a in ev.get("attendees", []) or []],
        "location": ev.get("location", ""),
        "meet": ev.get("hangoutLink"),
        "html_link": ev.get("htmlLink"),
    }


def freebusy(g: Google, identities: list[str], time_min: str, time_max: str, tz: str = DEFAULT_TZ) -> dict:
    """Busy blocks per identity. Each identity queries its own primary calendar."""
    out: dict[str, Any] = {}
    for alias in identities:
        ident = config.identity(alias)
        r = g.request(alias, "POST", f"{CALENDAR}/freeBusy", json={
            "timeMin": time_min, "timeMax": time_max, "timeZone": tz, "items": [{"id": ident.email}],
        })
        cal = (r.get("calendars") or {}).get(ident.email, {})
        out[alias] = {"busy": cal.get("busy", []), "errors": cal.get("errors", [])}
    return out


def agenda(g: Google, as_: str, days: int = 7, max_results: int = 50) -> list[dict]:
    config.identity(as_)
    now = datetime.now(timezone.utc)
    r = g.request(as_, "GET", f"{CALENDAR}/calendars/primary/events", params={
        "timeMin": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "timeMax": (now + timedelta(days=max(1, int(days)))).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": max(1, min(int(max_results), 250)),
    })
    return [_slim(e) for e in r.get("items", []) or []]


def create_event(g: Google, as_: str, summary: str, start: str, end: str, attendees: list[str] | None = None,
                 description: str = "", location: str = "", meet: bool = False, tentative: bool = False,
                 tz: str = DEFAULT_TZ) -> dict:
    config.identity(as_)
    if tentative and not summary.startswith(HOLD_PREFIX):
        summary = HOLD_PREFIX + summary
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": tz},
        "end": {"dateTime": end, "timeZone": tz},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    if tentative:
        body["status"] = "tentative"
        body["transparency"] = "transparent"  # a hold does not block freebusy
    params: dict[str, Any] = {}
    if meet:
        body["conferenceData"] = {"createRequest": {
            "requestId": str(uuid.uuid4()), "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
        params["conferenceDataVersion"] = 1
    ev = g.request(as_, "POST", f"{CALENDAR}/calendars/primary/events", params=params or None, json=body)
    return _slim(ev)


def _owned(g: Google, as_: str, event_id: str) -> dict:
    ident = config.identity(as_)
    ev = g.request(as_, "GET", f"{CALENDAR}/calendars/primary/events/{event_id}")
    org = (ev.get("organizer") or {})
    if not (org.get("self") or (org.get("email") or "").lower() == ident.email.lower()):
        raise NotOrganizer(f"{as_} did not organise event {event_id} (organiser: {org.get('email')}); refusing to change it")
    return ev


def update_event(g: Google, as_: str, event_id: str, **fields: Any) -> dict:
    _owned(g, as_, event_id)
    patch: dict[str, Any] = {}
    tz = fields.pop("tz", DEFAULT_TZ)
    for k in ("summary", "description", "location"):
        if fields.get(k) is not None:
            patch[k] = fields[k]
    if fields.get("start"):
        patch["start"] = {"dateTime": fields["start"], "timeZone": tz}
    if fields.get("end"):
        patch["end"] = {"dateTime": fields["end"], "timeZone": tz}
    if fields.get("attendees") is not None:
        patch["attendees"] = [{"email": a} for a in fields["attendees"]]
    if fields.get("confirm"):
        patch["status"] = "confirmed"
        patch["transparency"] = "opaque"
        cur = g.request(as_, "GET", f"{CALENDAR}/calendars/primary/events/{event_id}")
        if (cur.get("summary") or "").startswith(HOLD_PREFIX):
            patch["summary"] = patch.get("summary", cur["summary"][len(HOLD_PREFIX):])
    ev = g.request(as_, "PATCH", f"{CALENDAR}/calendars/primary/events/{event_id}", json=patch)
    return _slim(ev)


def delete_event(g: Google, as_: str, event_id: str) -> dict:
    _owned(g, as_, event_id)
    g.request(as_, "DELETE", f"{CALENDAR}/calendars/primary/events/{event_id}")
    return {"deleted": event_id, "as": as_}
