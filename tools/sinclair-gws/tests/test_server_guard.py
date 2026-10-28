"""Refusals must reach the model as error dicts, never as tool exceptions."""
from sinclair_gws import server


def test_unknown_identity_is_an_error_dict(monkeypatch):
    out = server.draft_new("someone-else", "a@b.c", "s", "b")
    assert out["error"] == "unknown_identity" and "someone-else" in out["message"]


def test_unknown_mailbox_on_search_is_an_error_dict():
    out = server.search("nobody", "is:unread")
    assert out["error"] == "unknown_identity"


def test_calendar_unknown_identity_is_an_error_dict():
    out = server.create_event("nobody", "x", "2026-09-30T09:00:00", "2026-09-30T09:15:00")
    assert out["error"] == "unknown_identity"


def test_every_tool_is_guarded():
    import inspect
    tools = [n for n, f in vars(server).items() if callable(f) and getattr(f, "__wrapped__", None)]
    assert set(tools) >= {"whoami", "search", "read", "draft_reply", "draft_new", "forward", "send_draft",
                          "freebusy", "agenda", "create_event", "update_event", "delete_event"}
