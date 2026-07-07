from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from core.logger import log
from core.ffprobe import is_video_file
from core.yaml_store import store
from core.scanner import scan_single_file

_suppressed: set[str] = set()
_suppressed_lock = threading.Lock()


def suppress_path(path: str) -> None:
    with _suppressed_lock:
        _suppressed.add(path)


def unsuppress_path(path: str) -> None:
    with _suppressed_lock:
        _suppressed.discard(path)


class _VideoHandler(FileSystemEventHandler):
    def __init__(
        self, library_name: str, loop: asyncio.AbstractEventLoop, enqueue_fn
    ) -> None:
        self._library_name = library_name
        self._loop = loop
        self._enqueue_fn = enqueue_fn
        self._debounce: dict[str, asyncio.TimerHandle] = {}

    def _schedule(self, path: str) -> None:
        if not is_video_file(path):
            return
        with _suppressed_lock:
            if path in _suppressed:
                return
        handle = self._debounce.pop(path, None)
        if handle:
            handle.cancel()
        self._debounce[path] = self._loop.call_later(2.0, self._fire, path)

    def _fire(self, path: str) -> None:
        self._debounce.pop(path, None)
        with _suppressed_lock:
            if path in _suppressed:
                return
        asyncio.run_coroutine_threadsafe(self._handle_file(path), self._loop)

    async def _handle_file(self, path: str) -> None:
        log.debug("File detected: %s", path)
        library = await store.get_library(self._library_name)
        if library is None:
            return
        await scan_single_file(path, self._library_name, library, self._enqueue_fn)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)


class LibraryWatcher:
    def __init__(self) -> None:
        self._observers: list[Observer] = []

    async def start(self, enqueue_fn) -> None:
        await self.stop()
        loop = asyncio.get_running_loop()
        libraries = await store.get_libraries()
        for name, lib in libraries.items():
            if not lib.watch:
                continue
            handler = _VideoHandler(name, loop, enqueue_fn)
            for dir_path in lib.paths:
                p = Path(dir_path)
                if not p.exists():
                    log.warning("Watch path does not exist: %s", dir_path)
                    continue
                observer = Observer()
                observer.schedule(handler, str(p), recursive=True)
                observer.daemon = True
                observer.start()
                self._observers.append(observer)
                log.info("Watching %s for library '%s'", dir_path, name)

    async def stop(self) -> None:
        for obs in self._observers:
            obs.stop()
        for obs in self._observers:
            obs.join(timeout=5)
        self._observers.clear()

    async def restart(self, enqueue_fn) -> None:
        await self.start(enqueue_fn)


watcher = LibraryWatcher()
