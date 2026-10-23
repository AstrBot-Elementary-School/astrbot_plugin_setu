"""只读插件配置的访问控制适配器。"""

from ...application.ports import AccessControlRepository
from ...domain.access_control import AccessPolicy
from ...shared.config.models import SafetyConfig


class ConfigAccessControlRepo(AccessControlRepository):
    def __init__(self, safety: SafetyConfig) -> None:
        self._safety = safety

    def get_policy(self, feature: str) -> AccessPolicy:
        for rule in self._safety.root:
            if rule.template_key == feature:
                return AccessPolicy(
                    mode=rule.mode.value,
                    blocked_sids=tuple(rule.blocked_sids),
                    whitelist_sids=tuple(rule.whitelist_sids),
                )
        return AccessPolicy()
