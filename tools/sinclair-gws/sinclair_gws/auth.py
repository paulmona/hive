"""Token minting by service-account domain-wide delegation.

Same mechanism as the gws-as wrapper this server replaces: one service-account key,
a short-lived token minted with subject=<user> per identity. Tokens are cached in
memory until shortly before expiry and never logged, returned, or written to disk.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2 import service_account

from .config import SCOPES, Identity, identity, sa_key_path


class KeyUnavailable(RuntimeError):
    pass


def key_identity() -> dict[str, str]:
    """Non-secret fields of the service-account key, for whoami. Never the private key."""
    path = sa_key_path()
    if not os.path.isfile(path):
        raise KeyUnavailable(f"service-account key not found at {path}")
    with open(path) as f:
        data = json.load(f)
    return {k: data.get(k, "") for k in ("client_email", "client_id", "project_id")}


class TokenSource:
    """Mints and caches one access token per identity."""

    _REFRESH_MARGIN = timedelta(minutes=5)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._creds: dict[str, service_account.Credentials] = {}

    def _credentials(self, ident: Identity) -> service_account.Credentials:
        creds = self._creds.get(ident.alias)
        if creds is None:
            path = sa_key_path()
            if not os.path.isfile(path):
                raise KeyUnavailable(f"service-account key not found at {path}")
            creds = service_account.Credentials.from_service_account_file(
                path, scopes=list(SCOPES), subject=ident.email
            )
            self._creds[ident.alias] = creds
        return creds

    def token(self, alias: str) -> str:
        ident = identity(alias)  # raises UnknownIdentity for anything outside the map
        with self._lock:
            creds = self._credentials(ident)
            expiry = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None
            if not creds.token or expiry is None or expiry - datetime.now(timezone.utc) < self._REFRESH_MARGIN:
                creds.refresh(Request())
            return creds.token
