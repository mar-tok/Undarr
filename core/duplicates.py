from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from typing import Callable

from core import db


def _partial_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read(4096)).hexdigest()
    except OSError:
        return ""


def _full_hash(path: str) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


async def scan_duplicates(
    library_names: list[str] | None,
    *,
    progress_fn: Callable | None = None,
    abort_event: asyncio.Event | None = None,
) -> dict:
    size_groups = await db.get_size_groups(library_names)
    if not size_groups:
        return {
            "groups": [],
            "total_duplicate_size": 0,
            "total_groups": 0,
            "not_hashed": 0,
        }

    sizes = [s for s, _ in size_groups]
    candidates = await db.get_files_by_sizes(sizes, library_names)

    by_size: dict[int, list[dict]] = defaultdict(list)
    for f in candidates:
        by_size[f["file_size"]].append(f)

    all_pairs = [(f["file_path"], f["library_name"]) for f in candidates]
    cache = await db.get_cached_hashes(all_pairs)

    total_files = len(candidates)
    hashed = 0
    confirmed_groups: list[dict] = []

    def _build_result() -> dict:
        groups = sorted(confirmed_groups, key=lambda g: g["file_size"], reverse=True)
        return {
            "groups": groups,
            "total_duplicate_size": sum(
                g["file_size"] * (len(g["files"]) - 1) for g in groups
            ),
            "total_groups": len(groups),
            "not_hashed": total_files - hashed,
        }

    for size, files in by_size.items():
        if abort_event and abort_event.is_set():
            return _build_result()

        partial_groups: dict[str, list[dict]] = defaultdict(list)
        for f in files:
            key = (f["file_path"], f["library_name"])
            cached = cache.get(key)
            if (
                cached
                and abs(cached["mtime"] - f["mtime"]) < 0.001
                and cached["partial_hash"]
            ):
                ph = cached["partial_hash"]
            else:
                ph = await asyncio.to_thread(_partial_hash, f["file_path"])
                if ph:
                    await db.upsert_file_hash(
                        f["file_path"], f["library_name"], f["mtime"], ph, ""
                    )
                    cache[key] = {
                        "mtime": f["mtime"],
                        "partial_hash": ph,
                        "full_hash": "",
                    }
            hashed += 1
            if ph:
                partial_groups[ph].append(f)
            if progress_fn:
                await progress_fn(hashed, total_files)

        for ph, pfiles in partial_groups.items():
            if len(pfiles) < 2:
                continue
            full_groups: dict[str, list[dict]] = defaultdict(list)
            for f in pfiles:
                key = (f["file_path"], f["library_name"])
                cached = cache.get(key)
                if (
                    cached
                    and abs(cached["mtime"] - f["mtime"]) < 0.001
                    and cached["full_hash"]
                ):
                    fh = cached["full_hash"]
                else:
                    fh = await asyncio.to_thread(_full_hash, f["file_path"])
                    if fh:
                        await db.upsert_file_hash(
                            f["file_path"],
                            f["library_name"],
                            f["mtime"],
                            cached["partial_hash"] if cached else ph,
                            fh,
                        )
                        if key in cache:
                            cache[key]["full_hash"] = fh
                if fh:
                    full_groups[fh].append(f)

            for fh, ffiles in full_groups.items():
                if len(ffiles) < 2:
                    continue
                confirmed_groups.append(
                    {
                        "file_size": size,
                        "full_hash": fh,
                        "files": ffiles,
                    }
                )

    return _build_result()
