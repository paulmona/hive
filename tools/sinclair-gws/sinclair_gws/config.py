"""Identity map and settings.

The identity map is the allowlist. An identity the server does not know cannot be
minted for, cannot be sent as, and cannot appear in a From header. Adding a third
identity is a code change here, on purpose.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    alias: str
    email: str
    display_name: str

    @property
    def from_header(self) -> str:
        return f"{self.display_name} <{self.email}>"

    @property
    def signature(self) -> str:
        return f"Regards,\n\n{self.display_name}\nViewBridge AI\n{self.email}"


IDENTITIES: dict[str, Identity] = {
    "sinclair": Identity("sinclair", "sinclair.viewbridge@viewbridge.ai", "Sinclair Viewbridge"),
    "paul": Identity("paul", "paul.monaghan@viewbridge.ai", "Paul Monaghan"),
}

# Reduced set from the design (section 2a). The Workspace Admin grant is wider until
# cutover; requesting a subset of a grant is fine, requesting more than it is a 401.
SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts.readonly",
)


def sa_key_path() -> str:
    return os.environ.get("SINCLAIR_GWS_SA_KEY_PATH", os.path.expanduser("~/.config/sinclair-gws/sa.json"))


def identity(alias: str) -> Identity:
    """Resolve an alias. Raises for anything outside the map; callers do not catch this."""
    try:
        return IDENTITIES[alias]
    except KeyError:
        raise UnknownIdentity(alias) from None


def identity_for_email(email: str) -> Identity:
    for ident in IDENTITIES.values():
        if ident.email.lower() == email.lower():
            return ident
    raise UnknownIdentity(email)


class UnknownIdentity(ValueError):
    def __init__(self, what: str):
        super().__init__(f"'{what}' is not an identity this server holds (known: {', '.join(IDENTITIES)})")
