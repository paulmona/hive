import base64
from email import message_from_bytes, policy

import pytest

from sinclair_gws import config, drafts, mail
from sinclair_gws.google import GoogleError


def b64(s): return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


ORIGINAL = {"id": "m1", "threadId": "t-orig", "payload": {
    "mimeType": "text/plain", "body": {"data": b64("Can we meet Tuesday?")},
    "headers": [
        {"name": "From", "value": "Counterparty <cp@example.com>"},
        {"name": "To", "value": "Paul Monaghan <paul.monaghan@viewbridge.ai>"},
        {"name": "Cc", "value": "Other <other@example.com>"},
        {"name": "Subject", "value": "Meeting"},
        {"name": "Date", "value": "Mon, 08 Sep 2026 09:00:00 -0400"},
        {"name": "Message-ID", "value": "<orig@example.com>"},
    ]}}


class FakeGoogle:
    def __init__(self, holder):
        self.holder = holder
        self.created = []
    def request(self, alias, method, url, **kw):
        if "/messages/m1" in url:
            if alias != self.holder:
                raise GoogleError(404, "nope")
            return ORIGINAL
        raise AssertionError(url)
    def gmail_create_draft(self, alias, raw_b64, thread_id):
        self.created.append((alias, raw_b64, thread_id))
        return {"id": "d1", "message": {"id": "dm1", "threadId": thread_id or "t-new"}}


def decode(raw_b64):
    return message_from_bytes(base64.urlsafe_b64decode(raw_b64 + "=" * (-len(raw_b64) % 4)), policy=policy.default)


def plain(m):
    return m.get_body(preferencelist=("plain",)).get_content()


def test_reply_sender_is_the_holder_not_an_argument():
    g = FakeGoogle("paul")
    out = drafts.draft_reply(g, "m1", "Tuesday works.")
    alias, raw, thread = g.created[0]
    m = decode(raw)
    assert alias == "paul" and out["as"] == "paul"
    assert m["From"] == "Paul Monaghan <paul.monaghan@viewbridge.ai>"
    assert thread == "t-orig" and out["thread_id"] == "t-orig"
    assert m["In-Reply-To"] == "<orig@example.com>" and "<orig@example.com>" in m["References"]
    assert m["Subject"] == "Re: Meeting"
    assert m["To"] == "Counterparty <cp@example.com>"
    body = plain(m)
    assert body.startswith("Tuesday works.") and "Regards,\n\nPaul Monaghan" in body and "> Can we meet Tuesday?" in body


def test_reply_from_sinclair_mailbox_goes_as_sinclair():
    g = FakeGoogle("sinclair")
    drafts.draft_reply(g, "m1", "Hi")
    assert decode(g.created[0][1])["From"] == "Sinclair Viewbridge <sinclair.viewbridge@viewbridge.ai>"


def test_reply_all_adds_others_but_not_self():
    g = FakeGoogle("paul")
    drafts.draft_reply(g, "m1", "Hi", reply_all=True)
    m = decode(g.created[0][1])
    assert "other@example.com" in m["Cc"] and "paul.monaghan" not in m["Cc"]


def test_reply_to_unknown_message_raises():
    with pytest.raises(mail.NotFound):
        drafts.draft_reply(FakeGoogle("nobody"), "m1", "Hi")


def test_draft_new_refuses_unknown_identity():
    with pytest.raises(config.UnknownIdentity):
        drafts.draft_new(FakeGoogle("paul"), "someone-else", "a@b.c", "s", "b")


def test_draft_new_from_is_display_named_and_unthreaded():
    g = FakeGoogle("paul")
    out = drafts.draft_new(g, "sinclair", "a@b.c", "Hello", "Body")
    alias, raw, thread = g.created[0]
    m = decode(raw)
    assert thread is None and m["From"] == "Sinclair Viewbridge <sinclair.viewbridge@viewbridge.ai>"
    assert m["Subject"] == "Hello" and out["draft_id"] == "d1"
    assert "Regards,\n\nSinclair Viewbridge\nViewBridge AI\nsinclair.viewbridge@viewbridge.ai" in plain(m)


def test_no_tool_accepts_a_from_header():
    import inspect
    from sinclair_gws import server
    for fn in (server.draft_reply, server.draft_new):
        assert "from" not in {p.lower() for p in inspect.signature(fn).parameters}


def test_forward_sender_is_holder_and_original_is_quoted():
    g = FakeGoogle("sinclair")
    out = drafts.forward(g, "m1", "paul.monaghan@viewbridge.ai", "FYI, this one is for you.")
    alias, raw, thread = g.created[0]
    m = decode(raw)
    assert alias == "sinclair" and m["From"] == "Sinclair Viewbridge <sinclair.viewbridge@viewbridge.ai>"
    assert m["To"] == "paul.monaghan@viewbridge.ai" and m["Subject"] == "Fwd: Meeting"
    assert thread == "t-orig"
    body = plain(m)
    assert body.startswith("FYI, this one is for you.")
    assert "---------- Forwarded message ----------" in body
    assert "From: Counterparty <cp@example.com>" in body and "Can we meet Tuesday?" in body
    assert "In-Reply-To" not in m


def test_forward_unknown_message_raises():
    with pytest.raises(mail.NotFound):
        drafts.forward(FakeGoogle("nobody"), "m1", "a@b.c")


def test_forward_has_no_identity_parameter():
    import inspect
    from sinclair_gws import server
    params = set(inspect.signature(server.forward).parameters)
    assert params == {"message_id", "to", "note"}


def test_draft_new_with_reference_joins_the_conversation_as_sinclair():
    g = FakeGoogle("paul")   # the customer's message lives in Paul's mailbox
    out = drafts.draft_new(g, "sinclair", "cp@example.com", "", "Paul asked me to find a time.", reference_message_id="m1")
    alias, raw, thread = g.created[0]
    m = decode(raw)
    assert alias == "sinclair" and thread is None                      # new thread, in Sinclair's mailbox
    assert m["From"] == "Sinclair Viewbridge <sinclair.viewbridge@viewbridge.ai>"
    assert m["Subject"] == "Re: Meeting"
    assert m["In-Reply-To"] == "<orig@example.com>" and "<orig@example.com>" in m["References"]
    assert "> Can we meet Tuesday?" in plain(m) and out["as"] == "sinclair"


def test_draft_new_reference_keeps_explicit_subject():
    g = FakeGoogle("paul")
    drafts.draft_new(g, "sinclair", "cp@example.com", "Scheduling", "Hi", reference_message_id="m1")
    assert decode(g.created[0][1])["Subject"] == "Scheduling"


def test_draft_new_unknown_reference_raises():
    with pytest.raises(mail.NotFound):
        drafts.draft_new(FakeGoogle("nobody"), "sinclair", "a@b.c", "s", "b", reference_message_id="m1")


def test_body_is_multipart_alternative_with_paragraph_html():
    g = FakeGoogle("paul")
    long = "A sentence that runs well past the seventy six character mark that Gmail wraps plain text at when it renders it.\n\nSecond paragraph."
    drafts.draft_reply(g, "m1", long)
    m = decode(g.created[0][1])
    assert m.get_content_type() == "multipart/alternative"
    plain = m.get_body(preferencelist=("plain",)).get_content()
    html = m.get_body(preferencelist=("html",)).get_content()
    assert plain.startswith(long) and "Regards,\n\nPaul Monaghan" in plain
    assert "<p>A sentence that runs well past" in html and "<p>Second paragraph.</p>" in html
    assert "<p>Regards,<br>" in html or "<p>Regards,</p>" in html
    assert 'class="gmail_quote"' in html and "Can we meet Tuesday?" in html
    assert "<script" not in html and "&lt;" not in plain
