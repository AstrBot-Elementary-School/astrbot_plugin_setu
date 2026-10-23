"""Shared SID access decision for commands, tools and pregeneration."""

from ...application.ports import AccessControlRepository


class AccessControlService:
    def __init__(self, repository: AccessControlRepository) -> None:
        self._repo = repository

    def check_access(self, feature: str, session_id: str | None) -> bool:
        return self._repo.get_policy(feature).allows(session_id)
