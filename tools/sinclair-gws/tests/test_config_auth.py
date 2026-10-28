import pytest

from sinclair_gws import auth, config


def test_identity_map_is_exactly_two():
    assert set(config.IDENTITIES) == {"sinclair", "paul"}


def test_from_header_has_display_name():
    assert config.identity("paul").from_header == "Paul Monaghan <paul.monaghan@viewbridge.ai>"
    assert config.identity("sinclair").from_header == "Sinclair Viewbridge <sinclair.viewbridge@viewbridge.ai>"


def test_unknown_alias_refused():
    with pytest.raises(config.UnknownIdentity):
        config.identity("someone-else")


def test_unknown_email_refused():
    with pytest.raises(config.UnknownIdentity):
        config.identity_for_email("attacker@viewbridge.ai")


def test_email_lookup_is_case_insensitive():
    assert config.identity_for_email("Paul.Monaghan@viewbridge.ai").alias == "paul"


def test_token_refuses_unknown_identity_before_touching_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SINCLAIR_GWS_SA_KEY_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(config.UnknownIdentity):
        auth.TokenSource().token("someone-else")


def test_token_fails_cleanly_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SINCLAIR_GWS_SA_KEY_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(auth.KeyUnavailable):
        auth.TokenSource().token("paul")


def test_key_identity_never_includes_private_key(tmp_path, monkeypatch):
    p = tmp_path / "sa.json"
    p.write_text('{"client_email":"x@y.iam","client_id":"1","project_id":"p","private_key":"SECRET"}')
    monkeypatch.setenv("SINCLAIR_GWS_SA_KEY_PATH", str(p))
    out = auth.key_identity()
    assert "private_key" not in out and "SECRET" not in str(out)
    assert out == {"client_email": "x@y.iam", "client_id": "1", "project_id": "p"}


def test_scopes_are_the_reduced_set():
    assert not any(s.endswith(("/drive", "/documents", "/spreadsheets")) for s in config.SCOPES)
