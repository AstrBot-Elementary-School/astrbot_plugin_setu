"""Disk-backed send cache for image delivery."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .logging import get_logger

logger = get_logger()

_IMAGE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


def guess_file_suffix(source: str, content_type: str | None = None) -> str:
    """Guess a file suffix for an image source."""
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type in _IMAGE_SUFFIXES:
        return _IMAGE_SUFFIXES[normalized_type]

    parsed = urlparse(source)
    guessed = Path(parsed.path).suffix.lower()
    if guessed in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        return ".jpg" if guessed == ".jpeg" else guessed

    fallback = mimetypes.guess_extension(normalized_type) if normalized_type else ""
    return fallback or ".img"


@dataclass(frozen=True)
class SendCacheWrite:
    """Reserved file paths for one cache write."""

    temp_path: Path
    final_path: Path


class DiskSendCache:
    """Small URL-addressed disk cache used before platform image sending."""

    def __init__(
        self,
        root: Path,
        *,
        enabled: bool = True,
        ttl_hours: int = 2,
        max_items: int = 200,
    ) -> None:
        self.root = root
        self.enabled = enabled
        self.ttl_seconds = max(1, int(ttl_hours)) * 60 * 60
        self.max_items = max(1, int(max_items))
        self._lock = asyncio.Lock()

    def _key(self, source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    async def get(self, source: str) -> Path | None:
        """Return a fresh cached file for the source URL, if present."""
        if not self.enabled:
            return None

        key = self._key(source)
        now = time.time()

        def find() -> Path | None:
            if not self.root.exists():
                return None
            for path in self.root.glob(f"{key}.*"):
                if path.suffix == ".part" or not path.is_file():
                    continue
                if now - path.stat().st_mtime > self.ttl_seconds:
                    continue
                return path
            return None

        return await asyncio.to_thread(find)

    async def reserve(
        self, source: str, content_type: str | None = None
    ) -> SendCacheWrite:
        """Reserve a temp path and final path for a source URL."""
        suffix = guess_file_suffix(source, content_type)
        key = self._key(source)
        final_path = self.root / f"{key}{suffix}"
        temp_path = self.root / f"{key}.{time.monotonic_ns()}{suffix}.part"

        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        return SendCacheWrite(temp_path=temp_path, final_path=final_path)

    async def commit(self, write: SendCacheWrite) -> Path:
        """Atomically promote a temp cache file to its final path."""

        def replace() -> None:
            write.temp_path.replace(write.final_path)
            write.final_path.touch()

        async with self._lock:
            await asyncio.to_thread(replace)
        return write.final_path

    async def discard(self, write: SendCacheWrite) -> None:
        """Delete a failed temp cache file."""

        def unlink() -> None:
            if write.temp_path.exists():
                write.temp_path.unlink()

        await asyncio.to_thread(unlink)

    async def cleanup(self) -> int:
        """Delete expired and overflow cache files."""
        now = time.time()

        def clean() -> int:
            if not self.root.exists():
                return 0

            removed = 0
            files: list[Path] = []
            for path in self.root.iterdir():
                if not path.is_file():
                    continue
                try:
                    age = now - path.stat().st_mtime
                except OSError:
                    continue
                if path.suffix == ".part" and age > 3600:
                    path.unlink(missing_ok=True)
                    removed += 1
                    continue
                if age > self.ttl_seconds:
                    path.unlink(missing_ok=True)
                    removed += 1
                    continue
                # DOCX 文件保留完整 TTL，避免异步上传期间被容量淘汰。
                if path.suffix != ".docx":
                    files.append(path)

            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for path in files[self.max_items :]:
                path.unlink(missing_ok=True)
                removed += 1
            return removed

        removed = await asyncio.to_thread(clean)
        if removed:
            logger.debug("[send_cache] cleaned %d cached files", removed)
        return removed


_send_cache: DiskSendCache | None = None


async def init_send_cache(
    data_dir: Path,
    *,
    enabled: bool,
    ttl_hours: int,
    max_items: int,
    cleanup_on_start: bool,
) -> DiskSendCache:
    """Initialize the process-wide send cache."""
    global _send_cache
    _send_cache = DiskSendCache(
        data_dir / "send_cache",
        enabled=enabled,
        ttl_hours=ttl_hours,
        max_items=max_items,
    )
    if cleanup_on_start:
        await _send_cache.cleanup()
    return _send_cache


def get_send_cache() -> DiskSendCache | None:
    """Return the configured send cache, if initialized."""
    return _send_cache


def clear_send_cache() -> None:
    """Clear the process-wide send cache reference."""
    global _send_cache
    _send_cache = None


def schedule_send_cache_cleanup(delay_seconds: float = 300.0) -> None:
    """Schedule a best-effort cache cleanup after current sends settle."""
    cache = _send_cache
    if cache is None:
        return

    async def cleanup_later() -> None:
        await asyncio.sleep(max(0.0, delay_seconds))
        await cache.cleanup()

    try:
        asyncio.create_task(cleanup_later())
    except RuntimeError:
        logger.debug("[send_cache] no running loop for delayed cleanup")
