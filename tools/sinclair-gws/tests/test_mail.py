import base64

from sinclair_gws import mail


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_plain_preferred_over_html():
    payload = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/plain", "body": {"data": b64("hello plain")}},
        {"mimeType": "text/html", "body": {"data": b64("<p>hello <b>html</b></p>")}},
    ]}
    assert mail.extract_body(payload) == "hello plain"


def test_html_stripped_when_no_plain():
    payload = {"mimeType": "text/html", "body": {"data": b64(
        "<html><head><style>p{color:red}</style></head><body><p>Hi&nbsp;Paul,</p><div>Line two</div></body></html>")}}
    assert mail.extract_body(payload) == "Hi Paul,\n\nLine two"


def test_nested_multipart_walked():
    payload = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("deep")}},
        ]},
        {"mimeType": "application/pdf", "body": {"attachmentId": "x"}},
    ]}
    assert mail.extract_body(payload) == "deep"


def test_headers_lowercased_and_message_shape():
    raw = {"id": "m1", "threadId": "t1", "labelIds": ["INBOX"], "snippet": "s", "payload": {
        "mimeType": "text/plain", "body": {"data": b64("body")},
        "headers": [{"name": "From", "value": "A <a@x>"}, {"name": "Subject", "value": "Hi"},
                    {"name": "Message-ID", "value": "<abc@x>"}]}}
    m = mail.to_message(raw, "paul")
    d = m.as_dict()
    assert d["holder"] == "paul" and d["from"] == "A <a@x>" and d["subject"] == "Hi"
    assert d["message_id_header"] == "<abc@x>" and d["body"] == "body" and d["thread_id"] == "t1"


class FakeGoogle:
    """Answers 404 for ids not in the given mailbox map."""
    def __init__(self, where: dict[str, str]):
        self.where = where
        self.calls = []
    def request(self, alias, method, url, **kw):
        self.calls.append((alias, url))
        mid = url.rsplit("/", 1)[-1]
        if self.where.get(mid) != alias:
            from sinclair_gws.google import GoogleError
            raise GoogleError(404, "not found")
        return {"id": mid, "threadId": "t", "payload": {"mimeType": "text/plain", "body": {"data": b64("x")}, "headers": []}}


def test_locate_finds_holder():
    g = FakeGoogle({"m1": "paul", "m2": "sinclair"})
    assert mail.locate(g, "m1") == "paul"
    assert mail.locate(g, "m2") == "sinclair"


def test_locate_unknown_raises_not_found():
    import pytest
    g = FakeGoogle({})
    with pytest.raises(mail.NotFound):
        mail.locate(g, "nope")


def test_search_refuses_unknown_mailbox():
    import pytest
    from sinclair_gws.config import UnknownIdentity
    with pytest.raises(UnknownIdentity):
        mail.search(FakeGoogle({}), "someone-else", "is:unread")
