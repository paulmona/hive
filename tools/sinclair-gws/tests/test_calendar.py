import pytest

from sinclair_gws import calendar, config


class FakeGoogle:
    def __init__(self, events=None):
        self.events = events or {}
        self.calls = []
    def request(self, alias, method, url, params=None, json=None, **kw):
        self.calls.append((alias, method, url, params, json))
        if method == "POST" and url.endswith("/events"):
            return {"id": "e1", "hangoutLink": "https://meet.google.com/abc" if json.get("conferenceData") else None, **json}
        if method == "POST" and url.endswith("/freeBusy"):
            return {"calendars": {json["items"][0]["id"]: {"busy": [{"start": "a", "end": "b"}]}}}
        if method == "GET" and "/events/" in url:
            return self.events[url.rsplit("/", 1)[-1]]
        if method == "GET" and url.endswith("/events"):
            return {"items": [{"id": "x", "summary": "S", "start": {"dateTime": "t"}, "end": {"dateTime": "u"}}]}
        if method in ("PATCH", "DELETE"):
            return {"id": url.rsplit("/", 1)[-1], **(json or {})} if method == "PATCH" else None
        raise AssertionError((method, url))


def test_meet_sets_conference_data_and_version_param():
    g = FakeGoogle()
    out = calendar.create_event(g, "sinclair", "Intro", "2026-09-10T10:00:00", "2026-09-10T10:30:00", meet=True)
    alias, method, url, params, body = g.calls[0]
    assert alias == "sinclair" and params == {"conferenceDataVersion": 1}
    assert body["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
    assert body["conferenceData"]["createRequest"]["requestId"]
    assert out["meet"] == "https://meet.google.com/abc"


def test_tentative_hold_is_prefixed_tentative_and_transparent():
    g = FakeGoogle()
    out = calendar.create_event(g, "paul", "Call with X", "2026-09-10T10:00:00", "2026-09-10T10:30:00", tentative=True)
    body = g.calls[0][4]
    assert body["summary"] == "HOLD: Call with X" and body["status"] == "tentative" and body["transparency"] == "transparent"
    assert "conferenceData" not in body and g.calls[0][3] is None
    assert out["summary"] == "HOLD: Call with X"


def test_unknown_identity_refused_before_any_call():
    g = FakeGoogle()
    with pytest.raises(config.UnknownIdentity):
        calendar.create_event(g, "someone-else", "x", "a", "b")
    assert g.calls == []


def test_delete_refused_when_not_organizer():
    g = FakeGoogle(events={"e9": {"id": "e9", "organizer": {"email": "paul.monaghan@viewbridge.ai"}}})
    with pytest.raises(calendar.NotOrganizer):
        calendar.delete_event(g, "sinclair", "e9")
    assert not any(c[1] == "DELETE" for c in g.calls)


def test_delete_allowed_for_organizer():
    g = FakeGoogle(events={"e9": {"id": "e9", "organizer": {"email": "sinclair.viewbridge@viewbridge.ai", "self": True}}})
    assert calendar.delete_event(g, "sinclair", "e9") == {"deleted": "e9", "as": "sinclair"}


def test_confirm_drops_hold_prefix_and_blocks():
    g = FakeGoogle(events={"e5": {"id": "e5", "summary": "HOLD: Call with X", "organizer": {"self": True}}})
    calendar.update_event(g, "paul", "e5", confirm=True)
    patch = [c for c in g.calls if c[1] == "PATCH"][0][4]
    assert patch["summary"] == "Call with X" and patch["status"] == "confirmed" and patch["transparency"] == "opaque"


def test_freebusy_queries_each_identity_as_itself():
    g = FakeGoogle()
    out = calendar.freebusy(g, ["sinclair", "paul"], "2026-09-10T00:00:00Z", "2026-09-11T00:00:00Z")
    assert [c[0] for c in g.calls] == ["sinclair", "paul"]
    assert out["paul"]["busy"] == [{"start": "a", "end": "b"}]


def test_agenda_slims_events():
    out = calendar.agenda(FakeGoogle(), "sinclair", 3)
    assert out[0]["id"] == "x" and out[0]["start"] == "t"
