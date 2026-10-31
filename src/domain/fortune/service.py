"""生成和刷新当前会话中的每日运势。"""

from datetime import date

from .entities import FortuneWeights


class FortuneService:
    def __init__(self, repository):
        self._repo = repository
        self._weights = FortuneWeights()

    async def get_or_create_fortune(self, request, force_refresh=False):
        return await self._repo.get_or_create(
            request, self._weights.calculate_star(), force_refresh
        )

    async def refresh_fortune(self, request):
        return await self.get_or_create_fortune(request, True)

    async def refresh_group_fortunes(self, session_id):
        return await self._repo.delete_fortunes(date.today().isoformat(), session_id)

    async def refresh_all_fortunes(self):
        return await self._repo.delete_fortunes(date.today().isoformat())
