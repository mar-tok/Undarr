from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Query

from app.models.responses import (
    StorageTreeOut,
    StorageEntry,
    LibraryFilesPageOut,
    LibraryFileOut,
    LibraryFileFiltersOut,
)
from core import db
from core.yaml_store import store

router = APIRouter(prefix="/api/storage", tags=["storage"])


def _parent_path(path: str) -> str | None:
    idx = path.rstrip("/").rfind("/")
    return path[:idx] if idx > 0 else None


@router.get("/tree", response_model=StorageTreeOut)
async def get_storage_tree(
    library: str = Query(...),
    path: str | None = Query(None),
):
    libs = await store.get_libraries()
    lib = libs.get(library)
    if not lib:
        return StorageTreeOut(
            library=library,
            path=path,
            parent=None,
            total_size=0,
            total_files=0,
            total_saved=0,
            entries=[],
        )

    files = await db.get_storage_files(library, path)
    savings = await db.get_storage_savings(library, path)

    if path is None:
        # Group by configured library paths
        roots = sorted({rp.rstrip("/") for rp in lib.paths}, key=len, reverse=True)

        def match_root(p: str) -> str | None:
            for rp in roots:
                if p.startswith(rp + "/") or p == rp:
                    return rp
            return None

        rp_files: dict[str, list] = {rp: [] for rp in roots}
        for fp, sz, vc in files:
            rp = match_root(fp)
            if rp:
                rp_files[rp].append((fp, sz, vc))

        saved_by_root: dict[str, int] = {rp: 0 for rp in roots}
        for k, v in savings.items():
            rp = match_root(k)
            if rp:
                saved_by_root[rp] += v

        entries = []
        for rp in roots:
            group = rp_files[rp]
            total = sum(sz for _, sz, _ in group)
            codecs: dict[str, int] = defaultdict(int)
            for _, _, vc in group:
                if vc:
                    codecs[vc] += 1
            entries.append(
                StorageEntry(
                    name=rp,
                    path=rp,
                    is_dir=True,
                    total_size=total,
                    file_count=len(group),
                    codecs=dict(codecs),
                    space_saved=saved_by_root[rp],
                )
            )
        entries.sort(key=lambda e: e.total_size, reverse=True)
        agg_size = sum(e.total_size for e in entries)
        agg_files = sum(e.file_count for e in entries)
        agg_saved = sum(e.space_saved for e in entries)
        return StorageTreeOut(
            library=library,
            path=None,
            parent=None,
            total_size=agg_size,
            total_files=agg_files,
            total_saved=agg_saved,
            entries=entries,
        )

    # Group by next path segment under the given path
    prefix = path.rstrip("/") + "/"
    prefix_len = len(prefix)

    dir_stats: dict[str, dict] = {}
    file_entries: list[StorageEntry] = []

    for fp, sz, vc in files:
        if not fp.startswith(prefix):
            continue
        rest = fp[prefix_len:]
        slash = rest.find("/")
        if slash == -1:
            saved = savings.get(fp, 0)
            codecs_map = {vc: 1} if vc else {}
            file_entries.append(
                StorageEntry(
                    name=rest,
                    path=fp,
                    is_dir=False,
                    total_size=sz,
                    file_count=1,
                    codecs=codecs_map,
                    space_saved=saved,
                )
            )
        else:
            seg = rest[:slash]
            dir_path = prefix + seg
            if dir_path not in dir_stats:
                dir_stats[dir_path] = {
                    "name": seg,
                    "size": 0,
                    "count": 0,
                    "codecs": defaultdict(int),
                    "saved": 0,
                }
            d = dir_stats[dir_path]
            d["size"] += sz
            d["count"] += 1
            if vc:
                d["codecs"][vc] += 1
            d["saved"] += savings.get(fp, 0)

    entries = []
    for dp, d in dir_stats.items():
        entries.append(
            StorageEntry(
                name=d["name"],
                path=dp,
                is_dir=True,
                total_size=d["size"],
                file_count=d["count"],
                codecs=dict(d["codecs"]),
                space_saved=d["saved"],
            )
        )
    entries.sort(key=lambda e: e.total_size, reverse=True)
    file_entries.sort(key=lambda e: e.total_size, reverse=True)
    entries.extend(file_entries)

    agg_size = sum(e.total_size for e in entries)
    agg_files = sum(e.file_count for e in entries)
    agg_saved = sum(e.space_saved for e in entries)

    return StorageTreeOut(
        library=library,
        path=path,
        parent=_parent_path(path),
        total_size=agg_size,
        total_files=agg_files,
        total_saved=agg_saved,
        entries=entries,
    )


@router.get("/files", response_model=LibraryFilesPageOut)
async def get_library_files(
    library: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("file_size"),
    sort_dir: str = Query("desc"),
    codec: str | None = Query(None),
    resolution: str | None = Query(None),
    container: str | None = Query(None),
    search: str | None = Query(None),
    status: str | None = Query(None),
):
    rows, total = await db.get_library_files_page(
        library,
        limit,
        offset,
        sort_by,
        sort_dir,
        codec,
        resolution,
        container,
        search,
        status,
    )
    return LibraryFilesPageOut(files=[LibraryFileOut(**r) for r in rows], total=total)


@router.get("/files/filters", response_model=LibraryFileFiltersOut)
async def get_library_file_filters(
    library: str = Query(...),
):
    data = await db.get_library_file_filters(library)
    return LibraryFileFiltersOut(**data)
