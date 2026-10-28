"""Tests for domain value objects."""

from __future__ import annotations

from astrbot_plugin_setu.src.domain.access_control import AccessPolicy
from astrbot_plugin_setu.src.infrastructure.sending.dto import SendAttemptResult


class TestAccessPolicy:
    def test_unrestricted(self) -> None:
        assert AccessPolicy().allows(None)

    def test_missing_sid_cannot_bypass_restrictions(self) -> None:
        assert not AccessPolicy(mode="blacklist").allows(None)
        assert not AccessPolicy(mode="blacklist").allows("123")
        assert not AccessPolicy(mode="whitelist").allows(None)

    def test_exact_sid(self) -> None:
        sid = "bot:GroupMessage:123"
        policy = AccessPolicy(mode="blacklist", blocked_sids=(sid,))
        assert not policy.allows(sid)
        assert policy.allows("bot:FriendMessage:123")
        assert policy.allows("other:GroupMessage:123")


class TestSendAttemptResult:
    """Test SendAttemptResult value object."""

    def test_message_id_string_is_one_id(self) -> None:
        """A single string message id should not be split into characters."""
        result = SendAttemptResult.success("123")

        assert result.message_ids == ("123",)

    def test_message_ids_are_trimmed_and_filtered(self) -> None:
        """Empty ids should not be carried into revoke scheduling."""
        result = SendAttemptResult.pending_delivery(
            "pending", ["  abc  ", "", "   ", 42]
        )

        assert result.message_ids == ("abc", "42")
