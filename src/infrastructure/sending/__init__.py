"""Sending layer — image sending strategies and implementations."""

from __future__ import annotations

from .doujinshi_sender import build_doujinshi_file_chain, get_doujinshi_file_name
from .dto import SendOptions
from .image_sender import ImageSender
from .revoke_scheduler import (
    get_revoke_scheduler,
    init_revoke_scheduler,
    schedule_revoke,
    stop_revoke_scheduler,
)
from .send_strategies import (
    DirectSendStrategy,
    ForwardSendStrategy,
    resolve_send_mode,
)

__all__ = [
    "ImageSender",
    "DirectSendStrategy",
    "ForwardSendStrategy",
    "SendOptions",
    "schedule_revoke",
    "get_revoke_scheduler",
    "init_revoke_scheduler",
    "stop_revoke_scheduler",
    "resolve_send_mode",
    "build_doujinshi_file_chain",
    "get_doujinshi_file_name",
]
