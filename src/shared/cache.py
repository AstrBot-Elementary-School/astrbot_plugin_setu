"""三个分类共用容量，写入中的文件由使用者持有。"""

import os
import threading
from pathlib import Path

LIMIT = 512 * 1024 * 1024


class Cache:
    def __init__(self, root, limit=LIMIT):
        self.root = Path(root)
        self.limit = limit
        self.lock = threading.RLock()
        self.active = {}
        self.removed = set()
        for name in ("fortune", "setu", "doujinshi"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def pin(self, path):
        with self.lock:
            self.active[path] = self.active.get(path, 0) + 1

    def release(self, path, keep=False):
        with self.lock:
            count = self.active[path] - 1
            if count:
                self.active[path] = count
            else:
                del self.active[path]
                if not keep or path in self.removed:
                    path.unlink(missing_ok=True)
                    self.removed.discard(path)

    def remove(self, path):
        with self.lock:
            if path in self.active:
                self.removed.add(path)
            else:
                path.unlink(missing_ok=True)

    def acquire(self, path):
        with self.lock:
            if not path.is_file() or path in self.removed:
                return False
            self.pin(path)
            return True

    def make_room(self, size):
        files = [p for p in self.root.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        for path in sorted(
            (p for p in files if p not in self.active), key=lambda p: p.stat().st_mtime
        ):
            if total + size <= self.limit:
                break
            total -= path.stat().st_size
            path.unlink()
        if total + size > self.limit:
            raise OSError(
                f"缓存空间不足：总上限 {self.limit} 字节，本次还需 {size} 字节"
            )

    def open(self, path, mode="w+b"):
        return BoundedFile(self, Path(path), mode)

    def write(self, path, data):
        with self.open(path) as file:
            file.write(data)


class BoundedFile:
    def __init__(self, cache, path, mode):
        self.cache = cache
        self.path = path
        with cache.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            cache.pin(path)
            try:
                self.file = path.open(mode)
            except BaseException:
                cache.release(path)
                raise

    def write(self, data):
        with self.cache.lock:
            self.file.flush()
            current = os.fstat(self.file.fileno()).st_size
            growth = max(0, self.file.tell() + len(data) - current)
            self.cache.make_room(growth)
            result = self.file.write(data)
            self.file.flush()
            return result

    def __getattr__(self, name):
        return getattr(self.file, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()
        self.cache.release(self.path, keep=args[0] is None)


_cache = None


def init_cache(root):
    global _cache
    _cache = Cache(root)
    with _cache.lock:
        _cache.make_room(0)
    return _cache


def get_cache():
    if _cache is None:
        raise RuntimeError("文件缓存尚未初始化")
    return _cache


def clear_cache():
    global _cache
    _cache = None
