"""使用框架提供的完整 SID。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    session_id: str


def get_event_session_identity(event) -> SessionIdentity:
    return SessionIdentity(event.unified_msg_origin)
