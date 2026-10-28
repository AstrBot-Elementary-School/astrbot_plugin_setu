"""Access-control domain value objects."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AccessPolicy:
    """Complete SID policy; group members share their conversation's access."""

    mode: Literal["none", "blacklist", "whitelist"] = "none"
    blocked_sids: tuple[str, ...] = ()
    whitelist_sids: tuple[str, ...] = ()

    def allows(self, session_id: str | None) -> bool:
        if self.mode == "none":
            return True
        # Old fortune records without SID must not bypass restricted policies.
        if (
            not session_id
            or len(session_id.split(":", 2)) != 3
            or not all(session_id.split(":", 2))
        ):
            return False
        if self.mode == "blacklist":
            return session_id not in self.blocked_sids
        if self.mode == "whitelist":
            return session_id in self.whitelist_sids
        raise ValueError(f"Invalid access-control mode: {self.mode}")
