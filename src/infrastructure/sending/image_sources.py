"""Resolve image references before accessing the local filesystem."""

from __future__ import annotations

import asyncio
import base64
import binascii
from pathlib import Path
from urllib.parse import unquote, urlparse

import astrbot.api.message_components as Comp

from ...shared import get_logger

logger = get_logger()


def local_image_path(ref: str | Path | None) -> Path | None:
    if not ref:
        return None
    text = str(ref)
    if text.startswith("file://"):
        parsed = urlparse(text)
        if parsed.netloc and parsed.netloc != "localhost":
            return None
        path = Path(unquote(parsed.path))
    elif "://" in text:
        return None
    else:
        path = Path(text)
    try:
        return path if path.exists() else None
    except OSError as exc:
        logger.warning("[send] failed to inspect image path: %s", exc)
        return None


async def read_image_bytes(comp: Comp.Image) -> bytes | None:
    if isinstance(comp.file, bytes):
        return comp.file
    if comp.file and comp.file.startswith("base64://"):
        try:
            return base64.b64decode(comp.file[9:], validate=True)
        except (binascii.Error, ValueError) as exc:
            logger.warning("[send] invalid base64 image: %s", exc)
            return None
    path = local_image_path(getattr(comp, "path", None)) or local_image_path(comp.file)
    if path is not None:
        try:
            return await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            logger.warning("[send] failed to read image: path=%s, error=%s", path, exc)
    return None
