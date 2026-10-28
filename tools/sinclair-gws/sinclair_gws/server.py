"""The MCP server. Tools are added one story at a time; this file holds only whoami."""
from __future__ import annotations

import logging

from mcp.server.mcpserver import MCPServer

from . import auth, calendar, config, drafts, mail, send
from .google import Google, GoogleError

# httpx logs every request at INFO; on a stdio server that is noise on stderr.
logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = MCPServer("sinclair-gws")
_google: Google | None = None

# Every refusal the package can raise, mapped to a stable error code. A refusal is a
# normal outcome the model should read, not a server traceback.
_REFUSALS = (
    (config.UnknownIdentity, "unknown_identity"),
    (mail.NotFound, "not_found"),
    (send.DraftNotFound, "not_found"),
    (calendar.NotOrganizer, "not_organizer"),
    (ValueError, "invalid"),
)


def guarded(fn):
    """Wrap a tool so package refusals come back as {"error": code, "message": ...}."""
    import functools

    @functools.wraps(fn)
    def inner(*a, **kw):
        try:
            return fn(*a, **kw)
        except GoogleError as e:
            return {"error": "google", "status": e.status, "message": str(e)}
        except Exception as e:  # noqa: BLE001
            for cls, code in _REFUSALS:
                if isinstance(e, cls):
                    return {"error": code, "message": str(e)}
            raise
    return inner


def google() -> Google:
    global _google
    if _google is None:
        _google = Google()
    return _google


@mcp.tool()
@guarded
def whoami() -> dict:
    """Which identities this server can act as, and whether it currently can.

    Returns the identity map, the non-secret fields of the service-account key, and
    for each identity whether a token mints and whether Gmail agrees who we are.
    Never returns a token or the private key.
    """
    out: dict = {"identities": [
        {"alias": i.alias, "email": i.email, "from": i.from_header} for i in config.IDENTITIES.values()
    ]}
    try:
        out["service_account"] = auth.key_identity()
    except auth.KeyUnavailable as e:
        out["service_account"] = {"error": str(e)}
        out["checks"] = {a: {"token": False, "gmail": None} for a in config.IDENTITIES}
        return out
    out["checks"] = {}
    for alias in config.IDENTITIES:
        check: dict = {"token": False, "gmail": None}
        try:
            google()._tokens.token(alias)
            check["token"] = True
            check["gmail"] = google().gmail_profile(alias).get("emailAddress")
        except GoogleError as e:
            check["gmail"] = f"error {e.status}"
        except Exception as e:  # noqa: BLE001 - surface the class, never the payload
            check["error"] = type(e).__name__
        out["checks"][alias] = check
    return out


@mcp.tool()
@guarded
def search(mailbox: str, query: str, max_results: int = 20) -> list[dict]:
    """Search one mailbox with a Gmail query. `mailbox` is `sinclair` or `paul`.

    Returns id, thread_id, holder, from, to, subject, date, snippet, labels per hit,
    newest first. Use the `id` with `read` for the body or with the draft tools.
    """
    return mail.search(google(), mailbox, query, max_results)


@mcp.tool()
@guarded
def read(message_id: str) -> dict:
    """Read one message by id, from whichever mailbox holds it.

    The `holder` field says which identity's mailbox the message lives in. That is what
    determines who a reply goes out as; there is no way to override it.
    """
    return mail.get(google(), message_id).as_dict()


@mcp.tool()
@guarded
def draft_reply(message_id: str, body: str, cc: str = "", reply_all: bool = False) -> dict:
    """Create a Gmail draft replying in-thread to `message_id`.

    The sender is the identity whose mailbox holds the message; there is no way to
    choose it. From carries the display name. In-Reply-To, References and threadId
    are set so the draft lands in the same thread. Returns draft_id, thread_id and the
    rendered From/To/Subject/body for the approval payload. Nothing is sent.
    """
    return drafts.draft_reply(google(), message_id, body, cc or None, reply_all)


@mcp.tool()
@guarded
def draft_new(as_: str, to: str, subject: str = "", body: str = "", cc: str = "",
              reference_message_id: str = "") -> dict:
    """Create a new Gmail draft as `as_`, which must be `sinclair` or `paul`.

    From carries the display name from the identity map. Pass `reference_message_id` to
    join a conversation that lives in the other mailbox (a customer wrote to Paul and
    Sinclair is taking over the scheduling as himself): the subject defaults to Re: the
    original and the threading headers point at it, so the recipient sees it under their
    own email. The draft is a new thread in the sender's mailbox. Nothing is sent.
    """
    return drafts.draft_new(google(), as_, to, subject, body, cc or None, reference_message_id or None)


@mcp.tool()
@guarded
def forward(message_id: str, to: str, note: str = "") -> dict:
    """Create a draft forwarding `message_id` to `to`, sent as whoever holds the message.

    This is how Paul gets into a thread that lives in Sinclair's mailbox: Sinclair forwards
    it. The sender is derived from the holding mailbox; there is no identity parameter.
    Returns draft_id and the rendered headers. Nothing is sent; use send_draft.
    """
    return drafts.forward(google(), message_id, to, note or None)


@mcp.tool()
@guarded
def send_draft(draft_id: str) -> dict:
    """Send an existing Gmail draft by id. The only send tool this server has.

    The draft is sent from whichever mailbox holds it, byte-for-byte as reviewed.
    Gmail deletes a draft when it is sent, so a draft id can only ever be sent once; a
    second call gets not_found. Returns the sent message id, thread id, and which
    identity it went out as. The Sent folder is the record.
    """
    return send.send_draft(google(), draft_id)


@mcp.tool()
@guarded
def freebusy(identities: list[str], time_min: str, time_max: str) -> dict:
    """Busy blocks for one or both identities (`sinclair`, `paul`) between two RFC 3339 times."""
    return calendar.freebusy(google(), identities, time_min, time_max)


@mcp.tool()
@guarded
def agenda(as_: str, days: int = 7) -> list[dict]:
    """Upcoming events on one identity's primary calendar for the next `days` days."""
    return calendar.agenda(google(), as_, days)


@mcp.tool()
@guarded
def create_event(as_: str, summary: str, start: str, end: str, attendees: list[str] | None = None,
                 description: str = "", location: str = "", meet: bool = False, tentative: bool = False) -> dict:
    """Create an event on `as_`'s primary calendar. `start`/`end` are RFC 3339 in America/Toronto.

    `meet=True` attaches a Google Meet link. `tentative=True` creates a HOLD: a tentative,
    non-blocking placeholder (the tier 1 hold on Paul's calendar); confirm it later with
    update_event(confirm=True). Returns the event with its id and any Meet link.
    """
    return calendar.create_event(google(), as_, summary, start, end, attendees, description, location, meet, tentative)


@mcp.tool()
@guarded
def update_event(as_: str, event_id: str, summary: str | None = None, start: str | None = None,
                 end: str | None = None, attendees: list[str] | None = None, description: str | None = None,
                 location: str | None = None, confirm: bool = False) -> dict:
    """Change an event `as_` organised. Refused for events organised by anyone else.

    `confirm=True` turns a HOLD into a confirmed, blocking event and drops the prefix.
    """
    return calendar.update_event(google(), as_, event_id, summary=summary, start=start, end=end,
                                     attendees=attendees, description=description, location=location, confirm=confirm)


@mcp.tool()
@guarded
def delete_event(as_: str, event_id: str) -> dict:
    """Delete an event `as_` organised. Refused for events organised by anyone else."""
    return calendar.delete_event(google(), as_, event_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
