from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from core.logger import log
from core.ffprobe import is_video_file
from core.yaml_store import store
from core.scanner import scan_single_file
from core import db

# Paths suppressed by the queue manager during file replacement.
# Checked by the watcher before scheduling any debounce, so
# shutil.move operations never trigger a re-queue.
_suppressed_paths: set[str] = set()
_suppressed_lock = threading.Lock()


def suppress_path(path: str) -> None:
    with _suppressed_lock:
        _suppressed_paths.add(path)


def unsuppress_path(path: str) -> None:
    with _suppressed_lock:
        _suppressed_paths.discard(path)


def is_suppressed(path: str) -> bool:
    with _suppressed_lock:
        return path in _suppressed_paths


class _VideoHandler(FileSystemEventHandler):
    def __init__(
        self,
        library_name: str,
        loop: asyncio.AbstractEventLoop,
        enqueue_fn,
        delay_seconds: float = 0,
        broadcast_fn=None,
    ) -> None:
        self._library_name = library_name
        self._loop = loop
        self._enqueue_fn = enqueue_fn
        self._delay = delay_seconds
        self._debounce: dict[str, asyncio.TimerHandle] = {}
        self._broadcast_fn = broadcast_fn

    def _schedule(self, path: str) -> None:
        if not is_video_file(path):
            return
        if is_suppressed(path):
            return
        handle = self._debounce.pop(path, None)
        if handle:
            handle.cancel()
        self._debounce[path] = self._loop.call_later(
            max(2.0, self._delay), self._fire, path
        )

    def _fire(self, path: str) -> None:
        self._debounce.pop(path, None)
        if is_suppressed(path):
            return
        asyncio.run_coroutine_threadsafe(self._handle_file(path), self._loop)

    async def _handle_file(self, path: str) -> None:
        log.debug("File detected: %s", path)
        if is_suppressed(path):
            return
        library = await store.get_library(self._library_name)
        if library is None:
            return
        try:
            st = Path(path).stat()
        except OSError:
            return
        if await db.is_processed(path, self._library_name, st.st_mtime):
            log.debug("Watcher ignoring %s (already processed)", path)
            return
        # Renames sometimes show up as separate create and delete events instead of a moved event
        old_path = await db.find_rename_candidate(path, self._library_name, st.st_size)
        if old_path:
            await db.rename_file(old_path, path, self._library_name, st.st_mtime)
            log.debug("Renamed tracked file: %s -> %s", old_path, path)
            if self._broadcast_fn:
                await self._broadcast_fn(
                    "library_files_changed", {"library_name": self._library_name}
                )
            return
        await scan_single_file(path, self._library_name, library, self._enqueue_fn)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            handle = self._debounce.pop(event.src_path, None)
            if handle:
                handle.cancel()
            if is_video_file(event.src_path):
                # Delay removal so rename detection in _handle_file can find the old record
                self._loop.call_later(
                    5.0,
                    lambda p=event.src_path: asyncio.run_coroutine_threadsafe(
                        self._remove_if_gone(p),
                        self._loop,
                    ),
                )

    async def _handle_rename(self, old_path: str, new_path: str) -> None:
        try:
            st = Path(new_path).stat()
        except OSError:
            return
        updated = await db.rename_file(
            old_path, new_path, self._library_name, st.st_mtime
        )
        if updated:
            log.debug("Renamed tracked file: %s -> %s", old_path, new_path)
            if self._broadcast_fn:
                await self._broadcast_fn(
                    "library_files_changed", {"library_name": self._library_name}
                )
        else:
            await scan_single_file(
                new_path,
                self._library_name,
                await store.get_library(self._library_name),
                self._enqueue_fn,
            )

    async def _remove_and_notify(self, path: str) -> None:
        log.debug("File removed: %s", path)
        await db.remove_library_file(path, self._library_name)
        if self._broadcast_fn:
            await self._broadcast_fn(
                "library_files_changed", {"library_name": self._library_name}
            )

    async def _remove_if_gone(self, path: str) -> None:
        if Path(path).exists():
            return
        await self._remove_and_notify(path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            log.debug("File moved: %s -> %s", event.src_path, event.dest_path)
            handle = self._debounce.pop(event.src_path, None)
            if handle:
                handle.cancel()
            if is_video_file(event.src_path) and is_video_file(event.dest_path):
                asyncio.run_coroutine_threadsafe(
                    self._handle_rename(event.src_path, event.dest_path),
                    self._loop,
                )
            else:
                if is_video_file(event.src_path):
                    asyncio.run_coroutine_threadsafe(
                        self._remove_and_notify(event.src_path),
                        self._loop,
                    )
                self._schedule(event.dest_path)


class LibraryWatcher:
    def __init__(self) -> None:
        self._observers: list[Observer] = []

    async def start(self, enqueue_fn, broadcast_fn=None) -> None:
        await self.stop()
        loop = asyncio.get_running_loop()
        libraries = await store.get_libraries()

        for name, lib in libraries.items():
            if not lib.watch:
                continue
            delay_seconds = lib.new_file_delay_seconds
            handler = _VideoHandler(
                name, loop, enqueue_fn, delay_seconds, broadcast_fn=broadcast_fn
            )
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
            await asyncio.to_thread(obs.join, timeout=5)
        self._observers.clear()

    async def restart(self, enqueue_fn, broadcast_fn=None) -> None:
        await self.start(enqueue_fn, broadcast_fn=broadcast_fn)


watcher = LibraryWatcher()
