"""运势仓储接口。"""

from typing import Protocol

from ...domain.fortune.entities import FortuneGenerationRequest, FortuneRecord


class FortuneRepository(Protocol):
    async def get_or_create(
        self, request: FortuneGenerationRequest, stars: int, refresh: bool = False
    ) -> FortuneRecord: ...
    async def delete_fortunes(
        self, date_str: str, session_id: str | None = None
    ) -> int: ...
