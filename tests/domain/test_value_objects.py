"""Tests for domain value objects."""

from __future__ import annotations

from astrbot_plugin_setu.src.application.setu import ImagePayload
from astrbot_plugin_setu.src.domain.access_control import AccessPolicy
from astrbot_plugin_setu.src.domain.fortune import FortuneResult, FortuneSeed
from astrbot_plugin_setu.src.domain.setu import SetuRequest
from astrbot_plugin_setu.src.infrastructure.sending import SendOptions
from astrbot_plugin_setu.src.infrastructure.sending.dto import SendAttemptResult


class TestSetuRequest:
    """Test SetuRequest value object."""

    def test_from_user_input(self) -> None:
        """Test creating SetuRequest from user input."""
        request = SetuRequest.from_user_input(3, ["girl", "cute"], False)
        assert request.count == 3
        assert request.tags == ("girl", "cute")
        assert request.r18 is False
        assert request.exclude_ai is True
        assert request.max_replenish_rounds == 3

    def test_with_tags(self) -> None:
        """Test creating new request with different tags."""
        request = SetuRequest.from_user_input(
            1, ["girl"], False, max_replenish_rounds=2
        )
        new_request = request.with_tags(["cat", "cute"])
        assert new_request.count == 1
        assert new_request.tags == ("cat", "cute")
        assert new_request.r18 is False
        assert new_request.max_replenish_rounds == 2


class TestImagePayload:
    """Test ImagePayload value object."""

    def test_empty_payload(self) -> None:
        """Test empty payload detection."""
        payload = ImagePayload((), (), False, ())
        assert payload.is_empty
        assert payload.count == 0

    def test_payload_with_urls(self) -> None:
        """Test payload with URLs."""
        payload = ImagePayload(("url1", "url2"), (), False, ("tag1",))
        assert not payload.is_empty
        assert payload.count == 2

    def test_payload_with_bytes(self) -> None:
        """Test payload with bytes."""
        payload = ImagePayload((), (b"data1", b"data2"), False, ())
        assert not payload.is_empty
        assert payload.count == 2

    def test_payload_count_uses_max(self) -> None:
        """Test count uses max of URLs and bytes."""
        payload = ImagePayload(("url1", "url2"), (b"data1",), False, ())
        assert payload.count == 2


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


class TestFortuneSeed:
    """Test FortuneSeed value object."""

    def test_for_today(self) -> None:
        """Test creating seed for today."""
        from datetime import date

        seed = FortuneSeed.for_today("user123")
        assert seed.user_id == "user123"
        assert seed.date_str == date.today().isoformat()

    def test_cache_key(self) -> None:
        """Test cache key generation."""
        seed = FortuneSeed("user123", "2026-05-09")
        assert seed.cache_key == "user123_2026-05-09"


class TestFortuneResult:
    """Test FortuneResult value object."""

    def test_max_stars(self) -> None:
        """Test max stars property."""
        seed = FortuneSeed("user123", "2026-05-09")
        result = FortuneResult(
            seed=seed,
            title="大吉",
            star_count=6,
            description="Lucky day!",
            extra_message="",
            theme_color="theme-red",
        )
        assert result.max_stars == 7
        assert result.star_count == 6


class TestSendOptions:
    """Test SendOptions value object."""

    def test_defaults(self) -> None:
        """Test default values."""
        options = SendOptions(
            send_mode="auto",
            use_html_card=False,
            auto_revoke=False,
            revoke_delay=30,
            r18_docx_mode=True,
        )
        assert options.send_mode == "auto"
        assert options.use_html_card is False
        assert options.auto_revoke is False
        assert options.revoke_delay == 30
        assert options.r18_docx_mode is True
        assert options.html_padding == 6
        assert options.html_gap == 6
        assert options.napcat_stream_chunk_kb == 64
        assert options.napcat_local_file_mode == "disabled"
        assert options.napcat_local_file_allowed_roots == ()


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
