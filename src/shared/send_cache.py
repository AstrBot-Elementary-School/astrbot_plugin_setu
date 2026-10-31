"""色图文件缓存，容量由共享缓存管理。"""

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from .cache import get_cache


@dataclass(frozen=True)
class SendCacheWrite:
    temp_path: Path
    final_path: Path


class DiskSendCache:
    def __init__(self, root, enabled=False):
        self.root = Path(root)
        self.enabled = enabled

    async def get(self, source):
        if not self.enabled:
            return None
        key = uuid5(NAMESPACE_URL, source).hex
        for path in self.root.glob(f"{key}.*"):
            if path.suffix != ".part" and get_cache().acquire(path):
                return path
        return None

    async def reserve(self, source, content_type=None):
        suffix = (
            Path(urlsplit(source).path).suffix
            or mimetypes.guess_extension((content_type or "").split(";")[0])
            or ".img"
        )
        final = self.root / f"{uuid5(NAMESPACE_URL, source).hex}{suffix}"
        temporary = final.with_name(final.name + "." + uuid4().hex + ".part")
        get_cache().pin(temporary)
        return SendCacheWrite(temporary, final)

    async def commit(self, write):
        cache = get_cache()
        with cache.lock:
            if write.final_path.exists():
                cache.release(write.temp_path)
                cache.pin(write.final_path)
                return write.final_path
            write.temp_path.replace(write.final_path)
            cache.release(write.temp_path, keep=True)
            cache.pin(write.final_path)
        return write.final_path

    async def discard(self, write):
        get_cache().release(write.temp_path)


_send_cache = None


async def init_send_cache(data_dir, enabled=False):
    global _send_cache
    _send_cache = DiskSendCache(Path(data_dir) / "cache" / "setu", enabled)
    return _send_cache


def get_send_cache():
    return _send_cache


def clear_send_cache():
    global _send_cache
    _send_cache = None
