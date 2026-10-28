"""Draft construction. The only way a message leaves this server is as a Gmail draft.

Two rules live here in code rather than in prose:
- The From header always comes from the identity map. No tool takes a From.
- A reply's sender is the identity whose mailbox holds the original. No tool takes an
  identity for a reply; `draft_reply` looks it up.
"""
from __future__ import annotations

import base64
from email.message import EmailMessage
from html import escape
from email.utils import getaddresses, parsedate_to_datetime

from . import config, mail
from .google import Google


def _addr_list(*headers: str) -> list[str]:
    out: list[str] = []
    for name, addr in getaddresses([h for h in headers if h]):
        if addr and addr.lower() not in {a.lower() for a in out}:
            out.append(addr if not name else f"{name} <{addr}>")
    return out


def _strip_self(addrs: list[str], self_email: str) -> list[str]:
    return [a for a in addrs if self_email.lower() not in a.lower()]


def _quote(original: mail.Message) -> str:
    h = original.headers
    when = h.get("date", "")
    try:
        when = parsedate_to_datetime(when).strftime("%a, %b %d, %Y at %I:%M %p")
    except Exception:  # noqa: BLE001 - keep the raw header if unparsable
        pass
    quoted = "\n".join(f"> {line}" for line in original.body.splitlines())
    return f"On {when}, {h.get('from', '')} wrote:\n{quoted}"


def _build(ident: config.Identity, to: list[str], cc: list[str], subject: str, body: str,
           in_reply_to: str | None = None, references: str | None = None, quoted: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = ident.from_header
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    text = body.rstrip() + "\n\n" + ident.signature
    if quoted:
        text += "\n\n" + quoted
    # Gmail rewraps long text/plain lines at ~76 columns on display, which puts hard
    # breaks mid-sentence. An HTML alternative with real paragraphs renders as written.
    msg.set_content(text)
    msg.add_alternative(_html(body, ident.signature, quoted), subtype="html")
    return msg


def _para(text: str) -> str:
    paras = [p for p in text.strip().split("\n\n")]
    return "".join(f"<p>{escape(p).replace(chr(10), '<br>')}</p>" for p in paras if p.strip())


def _html(body: str, signature: str, quoted: str | None) -> str:
    out = ['<div dir="ltr">', _para(body), _para(signature)]
    if quoted:
        head, _, rest = quoted.partition("\n")
        lines = [l[2:] if l.startswith("> ") else l for l in rest.split("\n")]
        out.append(f'<div class="gmail_quote">{escape(head)}<br>'
                   f'<blockquote class="gmail_quote" style="margin:0 0 0 .8ex;border-left:1px #ccc solid;padding-left:1ex">'
                   f'{_para(chr(10).join(lines)) or "<br>"}</blockquote></div>')
    out.append("</div>")
    return "".join(out)


def _create(g: Google, ident: config.Identity, msg: EmailMessage, thread_id: str | None) -> dict:
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    d = g.gmail_create_draft(ident.alias, raw, thread_id)
    return {
        "draft_id": d["id"],
        "message_id": d.get("message", {}).get("id"),
        "thread_id": d.get("message", {}).get("threadId") or thread_id,
        "as": ident.alias,
        "from": msg["From"],
        "to": msg["To"],
        "cc": msg.get("Cc", ""),
        "subject": msg["Subject"],
        "body": msg.get_body(preferencelist=("plain",)).get_content(),
    }


def draft_reply(g: Google, message_id: str, body: str, cc: str | None = None, reply_all: bool = False) -> dict:
    original = mail.get(g, message_id)          # raises NotFound; sets holder
    ident = config.identity(original.holder)    # the sender is the holder, full stop
    h = original.headers
    to = _addr_list(h.get("reply-to") or h.get("from", ""))
    extra_cc: list[str] = _addr_list(cc or "")
    if reply_all:
        others = _strip_self(_addr_list(h.get("to", ""), h.get("cc", "")), ident.email)
        extra_cc = _addr_list(", ".join(others + extra_cc))
        extra_cc = [a for a in extra_cc if a not in to]
    subject = h.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msgid = h.get("message-id")
    refs = " ".join(x for x in (h.get("references"), msgid) if x) or None
    msg = _build(ident, to, extra_cc, subject, body, in_reply_to=msgid, references=refs, quoted=_quote(original))
    return _create(g, ident, msg, original.thread_id)


def draft_new(g: Google, as_: str, to: str, subject: str, body: str, cc: str | None = None,
              reference_message_id: str | None = None) -> dict:
    """New draft from `as_`'s mailbox. With `reference_message_id`, join a conversation that
    lives in the other mailbox: subject defaults to Re: the original, In-Reply-To and
    References point at it, and it is quoted below. The draft is still a new thread in the
    sender's mailbox; the headers are for the recipient's client, so Sinclair's note lands
    under the customer's own email even though it comes from a different person."""
    ident = config.identity(as_)                 # refuses anything outside the map
    to_list = _addr_list(to)
    if not to_list:
        raise ValueError("draft_new needs at least one recipient")
    in_reply_to = references = quoted = None
    if reference_message_id:
        original = mail.get(g, reference_message_id)   # any mailbox; raises NotFound
        h = original.headers
        if not subject:
            subject = h.get("subject", "")
            if subject and not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
        in_reply_to = h.get("message-id")
        references = " ".join(x for x in (h.get("references"), in_reply_to) if x) or None
        quoted = _quote(original)
    msg = _build(ident, to_list, _addr_list(cc or ""), subject, body,
                 in_reply_to=in_reply_to, references=references, quoted=quoted)
    return _create(g, ident, msg, None)


def _forward_block(original: mail.Message) -> str:
    h = original.headers
    lines = ["---------- Forwarded message ----------",
             f"From: {h.get('from', '')}",
             f"Date: {h.get('date', '')}",
             f"Subject: {h.get('subject', '')}",
             f"To: {h.get('to', '')}"]
    if h.get("cc"):
        lines.append(f"Cc: {h['cc']}")
    return "\n".join(lines) + "\n\n" + original.body


def forward(g: Google, message_id: str, to: str, note: str | None = None) -> dict:
    """Forward from whichever mailbox holds the message, as that identity.

    Body is the note (if any), the signature, then the forwarded block with the
    original headers and body, matching Gmail's own layout. Kept in the holder's
    thread so it groups with the original in that mailbox. Attachments are not
    carried in v1. Creates a draft; sending is send_draft, like everything else.
    """
    original = mail.get(g, message_id)
    ident = config.identity(original.holder)
    to_list = _addr_list(to)
    if not to_list:
        raise ValueError("forward needs at least one recipient")
    subject = original.headers.get("subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"
    msg = _build(ident, to_list, [], subject, note or "", quoted=_forward_block(original))
    return _create(g, ident, msg, original.thread_id)
