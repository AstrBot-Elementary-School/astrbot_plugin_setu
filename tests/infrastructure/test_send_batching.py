"""Tests for send batching logic."""

from __future__ import annotations

from astrbot_plugin_setu.src.infrastructure.sending.send_batching import (
    DIRECT_MAX_IMAGES,
    split_send_batches,
)


def test_split_send_batches_respects_image_cap_in_direct_mode():
    """Direct mode should split at 8-image boundary regardless of size."""
    # 10 tiny images, each 100 bytes base64
    sizes = [100] * 10
    batches = split_send_batches(sizes, "image", max_images=DIRECT_MAX_IMAGES)
    assert len(batches) == 2
    assert batches[0] == list(range(8))  # First 8
    assert batches[1] == [8, 9]  # Remaining 2


def test_split_send_batches_forward_mode_ignores_image_cap():
    """Forward mode should ignore image count cap, only respect byte limit."""
    # 10 tiny images, total well under byte limit
    sizes = [100] * 10
    batches = split_send_batches(sizes, "forward", max_images=DIRECT_MAX_IMAGES)
    assert len(batches) == 1
    assert batches[0] == list(range(10))


def test_split_send_batches_oversized_image_gets_own_batch():
    """An image larger than the byte limit should still get its own batch."""
    max_bytes = 1000
    sizes = [500, 2000, 500]  # Middle image is over limit
    batches = split_send_batches(sizes, "image", max_base64_bytes=max_bytes)
    assert len(batches) == 3
    assert batches[0] == [0]
    assert batches[1] == [1]  # Oversized, alone
    assert batches[2] == [2]
