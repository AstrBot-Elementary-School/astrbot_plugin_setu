"""Setu application DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageMetadata:
    image_url: str
    source_url: str
    tags: tuple[str, ...] = ()
    download_url: str | None = None


@dataclass(frozen=True)
class ImagePayload:
    """Fetched image data ready for adapter-level delivery."""

    urls: tuple[str, ...]
    raw_bytes: tuple[bytes, ...]
    r18: bool
    tags: tuple[str, ...]
    file_paths: tuple[Path, ...] = ()
    items: tuple[Path | bytes, ...] = ()
    images: tuple[ImageMetadata, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Check if payload contains no data."""
        return (
            not self.urls
            and not self.raw_bytes
            and not self.file_paths
            and not self.items
        )

    @property
    def count(self) -> int:
        """Return number of images in payload."""
        if self.items:
            return len(self.items)
        return max(len(self.urls), len(self.raw_bytes), len(self.file_paths))


@dataclass(frozen=True)
class SetuImagesResult:
    """Application result for a Setu image request."""

    payload: ImagePayload | None
    notice: str | None = None
