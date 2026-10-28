import pytest

from sinclair_gws import send
from sinclair_gws.google import GoogleError


class FakeGoogle:
    """Mimics Gmail: a sent draft is deleted, so a second get/send is a 404."""
    def __init__(self, drafts: dict[str, str]):
        self.drafts = drafts  # draft_id -> holder alias
        self.sent = []
    def gmail_get_draft(self, alias, draft_id):
        if self.drafts.get(draft_id) != alias:
            raise GoogleError(404, "not found")
        return {"id": draft_id}
    def gmail_send_draft(self, alias, draft_id):
        if self.drafts.get(draft_id) != alias:
            raise GoogleError(404, "not found")
        self.sent.append((alias, draft_id))
        del self.drafts[draft_id]
        return {"id": f"sent-{draft_id}", "threadId": "t1"}


def test_sends_from_holding_mailbox():
    g = FakeGoogle({"d1": "paul"})
    out = send.send_draft(g, "d1")
    assert g.sent == [("paul", "d1")]
    assert out["as"] == "paul" and out["message_id"] == "sent-d1" and out["thread_id"] == "t1"


def test_second_send_is_not_found_and_not_transmitted():
    g = FakeGoogle({"d1": "sinclair"})
    send.send_draft(g, "d1")
    with pytest.raises(send.DraftNotFound):
        send.send_draft(g, "d1")
    assert len(g.sent) == 1


def test_unknown_draft_raises_before_any_send():
    g = FakeGoogle({})
    with pytest.raises(send.DraftNotFound):
        send.send_draft(g, "ghost")
    assert g.sent == []


def test_race_where_draft_vanishes_between_locate_and_send():
    class Racy(FakeGoogle):
        def gmail_send_draft(self, alias, draft_id):
            raise GoogleError(404, "gone")
    g = Racy({"d1": "paul"})
    with pytest.raises(send.DraftNotFound):
        send.send_draft(g, "d1")


def test_no_compose_and_send_path_exists():
    """The server must not be able to send anything that is not an existing draft."""
    import pathlib
    src = pathlib.Path(send.__file__).parent
    offenders = [f.name for f in src.glob("*.py") if "messages/send" in f.read_text() or "messages.send" in f.read_text()]
    assert offenders == []


def test_send_tool_takes_only_a_draft_id():
    import inspect
    from sinclair_gws import server
    assert list(inspect.signature(server.send_draft).parameters) == ["draft_id"]


def test_nothing_is_written_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    send.send_draft(FakeGoogle({"d1": "paul"}), "d1")
    assert list(tmp_path.rglob("*")) == []
