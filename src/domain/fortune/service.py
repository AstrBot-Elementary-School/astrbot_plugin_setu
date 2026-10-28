"""Fortune domain service for generating fortunes.

Extracts business logic from FortuneCore into a pure domain service.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date

from ...application.ports import FortuneRepository
from .entities import (
    FortuneGenerationRequest,
    FortuneRecord,
    FortuneTheme,
    FortuneWeights,
)


class FortuneService:
    """Domain service for fortune generation and retrieval.

    Provides pure business logic for fortune operations,
    separate from persistence and infrastructure concerns.
    """

    def __init__(
        self,
        repository: FortuneRepository,
        weights: FortuneWeights | None = None,
        theme: FortuneTheme | None = None,
    ) -> None:
        """Initialize fortune service.

        Args:
            repository: Fortune repository for persistence
            weights: Fortune weights (uses default if None)
            theme: Fortune theme (uses default if None)
        """
        self._repo = repository
        self._weights = weights or FortuneWeights.default()
        self._theme = theme or FortuneTheme.default()

    async def get_or_create_fortune(
        self, request: FortuneGenerationRequest, force_refresh: bool = False
    ) -> FortuneRecord:
        """Get or create fortune for user.

        Args:
            request: Fortune generation request
            force_refresh: If True, generate new fortune even if one exists

        Returns:
            FortuneRecord

        Raises:
            FortuneException: If fortune generation fails
        """
        # Try to get existing fortune
        existing = await self._repo.get_today_fortune(request)
        if existing and not force_refresh:
            updated = await self._prepare_existing_record(existing, request)
            updated = updated.with_last_view_date(request.date_str)
            await self._repo.save_fortune(updated)
            return updated

        # Generate new fortune
        star_count = self._weights.calculate_star()
        title = self._theme.get_title(star_count)
        description = self._theme.get_message(star_count)
        theme_color = self._theme.get_theme_color(star_count)
        extra_message = self._theme.extra_message

        record = FortuneRecord.create_new(
            user_id=request.user_id,
            username=request.username,
            date_str=request.date_str,
            title=title,
            star_count=star_count,
            description=description,
            extra_message=extra_message,
            theme_color=theme_color,
            group_id=request.group_id,
            session_id=request.session_id,
        )

        await self._repo.save_fortune(record)
        return record

    async def refresh_fortune(self, request: FortuneGenerationRequest) -> FortuneRecord:
        """Refresh user's fortune (generate new).

        Args:
            request: Fortune generation request

        Returns:
            New FortuneRecord
        """
        # Delete existing fortune first
        await self._repo.delete_fortune(request.user_id, request.date_str)

        # Delete cached image
        await self._repo.delete_cached_image(request.user_id, request.date_str)

        # Generate new fortune
        return await self.get_or_create_fortune(request, force_refresh=True)

    async def refresh_group_fortunes(
        self, group_id: str, date_str: str | None = None
    ) -> int:
        """Refresh all fortunes for a group.

        Args:
            group_id: Group identifier
            date_str: Date string (uses today if None)

        Returns:
            Number of fortunes refreshed
        """
        if date_str is None:
            date_str = date.today().isoformat()

        count = await self._repo.delete_group_fortunes(group_id, date_str)

        # Note: This deletes records but doesn't regenerate them.
        # Regeneration happens when users request their fortune again.

        return count

    async def refresh_all_fortunes(self, date_str: str | None = None) -> int:
        """Refresh all fortunes for a given date.

        Args:
            date_str: Date string (uses today if None)

        Returns:
            Number of fortunes deleted
        """
        if date_str is None:
            date_str = date.today().isoformat()

        return await self._repo.delete_all_fortunes(date_str)

    async def pregenerate_active_users(self, days: int = 3) -> int:
        """Pregenerate fortunes for active users.

        Args:
            days: Number of days to look back for activity

        Returns:
            Number of fortunes pregenerated
        """
        records = await self.pregenerate_active_user_records(
            days=days, include_existing=False
        )
        return len(records)

    async def pregenerate_active_user_records(
        self,
        days: int = 3,
        *,
        include_existing: bool = False,
        access_filter: Callable[[FortuneGenerationRequest], Awaitable[bool]]
        | None = None,
    ) -> list[FortuneRecord]:
        """Ensure today's fortune records exist for recently active users.

        Args:
            days: Number of days to look back for activity
            include_existing: Include existing records in the returned list

        Returns:
            Records that were created, plus existing records when requested
        """
        today_str = date.today().isoformat()
        active_requests = await self._repo.get_active_fortune_requests(
            days, date_str=today_str
        )

        records: list[FortuneRecord] = []
        for request in active_requests:
            if access_filter is not None and not await access_filter(request):
                continue
            existing = await self._repo.get_today_fortune(request)
            if existing:
                existing = await self._prepare_existing_record(existing, request)
                if include_existing:
                    records.append(existing)
                continue

            records.append(await self.get_or_create_fortune(request))

        return records

    async def _prepare_existing_record(
        self, existing: FortuneRecord, request: FortuneGenerationRequest
    ) -> FortuneRecord:
        """Refresh mutable display fields while preserving fortune result."""
        changed = (
            existing.username != request.username
            or existing.group_id != request.group_id
            or existing.session_id != request.session_id
        )
        if not changed:
            return existing

        updated = existing.with_presentation(
            username=request.username,
            group_id=request.group_id,
            session_id=request.session_id,
            invalidate_image_cache=True,
        )
        await self._repo.delete_cached_image(existing.user_id, existing.date_str)
        await self._repo.save_fortune(updated)
        return updated

    async def update_image_cache(
        self, record: FortuneRecord, image_data: bytes, img_url: str | None
    ) -> FortuneRecord:
        """Update image cache for fortune record.

        Args:
            record: Fortune record
            image_data: Image bytes
            img_url: Image URL

        Returns:
            Updated FortuneRecord with image_cached=True
        """
        await self._repo.save_cached_image(
            record.user_id, record.date_str, image_data, img_url
        )
        return record.with_image_cache(img_url)

    async def get_cached_image(self, user_id: str, date_str: str) -> bytes | None:
        """Get cached image data.

        Args:
            user_id: User identifier
            date_str: Date string

        Returns:
            Image bytes if cache exists, None otherwise
        """
        cache_path = await self._repo.get_cached_image_path(user_id, date_str)
        if cache_path:
            try:
                import asyncio

                return await asyncio.to_thread(cache_path.read_bytes)
            except OSError as e:
                logging.debug("Failed to read cached image: %s", e)
        return None

    async def cleanup_cache(self, date_str: str | None = None) -> int:
        """Clean up expired cache files.

        Args:
            date_str: Date string (uses today if None)

        Returns:
            Number of files deleted
        """
        if date_str is None:
            date_str = date.today().isoformat()

        return await self._repo.cleanup_expired_cache(date_str)

    def format_stars(self, star_count: int, max_count: int = 7) -> str:
        """Format star display.

        Args:
            star_count: Number of stars
            max_count: Maximum stars

        Returns:
            Formatted star string (e.g., "★★★★☆☆☆☆")
        """
        filled = "★" * star_count
        empty = "☆" * (max_count - star_count)
        return filled + empty
