"""AstrBot 管理员及群管理员权限。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


class PermissionService:
    @staticmethod
    def is_admin(event: AstrMessageEvent) -> bool:
        return event.is_admin() or event.message_obj.sender.role in ("admin", "owner")

    @staticmethod
    def is_super_user(event: AstrMessageEvent) -> bool:
        return event.is_admin()

    @staticmethod
    def require_admin(event: AstrMessageEvent) -> tuple[bool, str]:
        return (
            (True, "")
            if PermissionService.is_admin(event)
            else (False, "此操作需要管理员权限。")
        )

    @staticmethod
    def require_super_user(event: AstrMessageEvent) -> tuple[bool, str]:
        return (
            (True, "")
            if PermissionService.is_super_user(event)
            else (False, "此操作需要超级管理员权限。")
        )
