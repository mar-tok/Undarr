from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

import config
from core.logger import log

_db: aiosqlite.Connection | None = None

SCHEMA = """\
CREATE TABLE IF NOT EXISTS job_history (
    id               TEXT PRIMARY KEY,
    library_name     TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    status           TEXT NOT NULL,
    old_size_bytes   INTEGER NOT NULL,
    new_size_bytes   INTEGER,
    started_at       TEXT NOT NULL,
    finished_at      TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    ffmpeg_log       TEXT NOT NULL DEFAULT '',
    error_message    TEXT,
    dismissed        INTEGER NOT NULL DEFAULT 0,
    preset_name      TEXT NOT NULL DEFAULT '',
    device_name      TEXT NOT NULL DEFAULT ''
);
"""

PROCESSED_SCHEMA = """\
CREATE TABLE IF NOT EXISTS processed_files (
    file_path     TEXT NOT NULL,
    library_name  TEXT NOT NULL,
    mtime         REAL NOT NULL,
    processed_at  TEXT NOT NULL,
    PRIMARY KEY (file_path, library_name)
);
"""

LIBRARY_FILES_SCHEMA = """\
CREATE TABLE IF NOT EXISTS library_files (
    file_path      TEXT NOT NULL,
    library_name   TEXT NOT NULL,
    video_codec    TEXT NOT NULL DEFAULT '',
    resolution_h   INTEGER NOT NULL DEFAULT 0,
    file_size      INTEGER NOT NULL DEFAULT 0,
    mtime          REAL NOT NULL DEFAULT 0,
    bitrate_kbps   INTEGER NOT NULL DEFAULT 0,
    container      TEXT NOT NULL DEFAULT '',
    audio_codec    TEXT NOT NULL DEFAULT '',
    audio_channels INTEGER NOT NULL DEFAULT 0,
    duration       REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (file_path, library_name)
);
"""


async def _column_names(conn: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def init_db() -> None:
    global _db
    db_path = config.DATA_DIR / "undarr.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(db_path))
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.executescript(PROCESSED_SCHEMA)
    await _db.executescript(LIBRARY_FILES_SCHEMA)
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_libfiles_lib_path ON library_files (library_name, file_path)"
    )
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobhistory_status_finished ON job_history (status, finished_at)"
    )
    await _db.commit()

    cols = await _column_names(_db, "job_history")
    if "dismissed" not in cols:
        await _db.execute(
            "ALTER TABLE job_history ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0"
        )
        await _db.commit()
    if "preset_name" not in cols:
        await _db.execute(
            "ALTER TABLE job_history ADD COLUMN preset_name TEXT NOT NULL DEFAULT ''"
        )
        await _db.execute(
            "ALTER TABLE job_history ADD COLUMN device_name TEXT NOT NULL DEFAULT ''"
        )
        await _db.commit()

    log.info("Database initialized at %s", db_path)


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def get_db() -> aiosqlite.Connection:
    assert _db is not None, "Database not initialized"
    return _db


async def insert_job_history(
    *,
    id: str,
    library_name: str,
    file_path: str,
    status: str,
    old_size_bytes: int,
    new_size_bytes: int | None,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    ffmpeg_log: str,
    error_message: str | None,
    dismissed: bool = False,
    preset_name: str = "",
    device_name: str = "",
) -> None:
    db = get_db()
    await db.execute(
        """INSERT INTO job_history
           (id, library_name, file_path, status, old_size_bytes, new_size_bytes,
            started_at, finished_at, duration_seconds, ffmpeg_log, error_message, dismissed,
            preset_name, device_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            id,
            library_name,
            file_path,
            status,
            old_size_bytes,
            new_size_bytes,
            started_at,
            finished_at,
            duration_seconds,
            ffmpeg_log,
            error_message,
            int(dismissed),
            preset_name,
            device_name,
        ),
    )
    await db.commit()


HISTORY_SORT_COLUMNS = {
    "finished_at",
    "file_path",
    "library_name",
    "old_size_bytes",
    "new_size_bytes",
    "status",
}


async def get_history(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    sort_by: str = "finished_at",
    sort_dir: str = "desc",
    exclude_dismissed: bool = False,
) -> list[dict]:
    db = get_db()
    conditions: list[str] = []
    params: list = []
    if exclude_dismissed:
        conditions.append("dismissed = 0")
    if status:
        conditions.append("status = ?")
        params.append(status)
    if search:
        conditions.append("file_path LIKE ?")
        params.append(f"%{search}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    col = sort_by if sort_by in HISTORY_SORT_COLUMNS else "finished_at"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    cursor = await db.execute(
        f"""SELECT id, library_name, file_path, status, old_size_bytes, new_size_bytes,
                   started_at, finished_at, duration_seconds, error_message,
                   preset_name, device_name
            FROM job_history {where}
            ORDER BY {col} {direction} LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_history_entry(job_id: str) -> dict | None:
    db = get_db()
    cursor = await db.execute(
        "SELECT id, library_name, file_path, status, old_size_bytes FROM job_history WHERE id = ?",
        (job_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def dismiss_history_entries(job_ids: list[str]) -> int:
    if not job_ids:
        return 0
    db = get_db()
    placeholders = ",".join("?" for _ in job_ids)
    cursor = await db.execute(
        f"UPDATE job_history SET dismissed = 1 WHERE id IN ({placeholders})",
        job_ids,
    )
    await db.commit()
    return cursor.rowcount


async def search_files(
    query: str,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "finished_at",
    sort_dir: str = "desc",
    status: str | None = None,
) -> tuple[list[dict], int]:
    db = get_db()
    pattern = f"%{query}%"
    conditions = ["file_path LIKE ?"]
    params: list = [pattern]
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(conditions)
    cursor = await db.execute(
        f"SELECT COUNT(*) FROM job_history {where}",
        params,
    )
    total = (await cursor.fetchone())[0]
    col = sort_by if sort_by in HISTORY_SORT_COLUMNS else "finished_at"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    cursor = await db.execute(
        f"""SELECT id, library_name, file_path, status, old_size_bytes, new_size_bytes,
                  started_at, finished_at, duration_seconds, error_message,
                  preset_name, device_name
           FROM job_history {where}
           ORDER BY {col} {direction} LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows], total


async def get_job_log(job_id: str) -> str | None:
    db = get_db()
    cursor = await db.execute(
        "SELECT ffmpeg_log FROM job_history WHERE id = ?", (job_id,)
    )
    row = await cursor.fetchone()
    return row["ffmpeg_log"] if row else None


async def mark_processed(file_path: str, library_name: str, mtime: float) -> None:
    db = get_db()
    await db.execute(
        """INSERT OR REPLACE INTO processed_files (file_path, library_name, mtime, processed_at)
           VALUES (?, ?, ?, ?)""",
        (file_path, library_name, mtime, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


async def is_processed(file_path: str, library_name: str, current_mtime: float) -> bool:
    db = get_db()
    cursor = await db.execute(
        "SELECT mtime FROM processed_files WHERE file_path = ? AND library_name = ?",
        (file_path, library_name),
    )
    row = await cursor.fetchone()
    if row is None:
        return False
    return abs(row["mtime"] - current_mtime) < 0.001


async def clear_processed(library_name: str) -> int:
    db = get_db()
    cursor = await db.execute(
        "DELETE FROM processed_files WHERE library_name = ?",
        (library_name,),
    )
    await db.commit()
    return cursor.rowcount


async def remove_processed(file_path: str, library_name: str) -> None:
    db = get_db()
    await db.execute(
        "DELETE FROM processed_files WHERE file_path = ? AND library_name = ?",
        (file_path, library_name),
    )
    await db.commit()


async def clear_history(clear_processed: bool = True) -> int:
    db = get_db()
    cursor = await db.execute("DELETE FROM job_history")
    if clear_processed:
        await db.execute("DELETE FROM processed_files")
    await db.commit()
    return cursor.rowcount


async def upsert_library_file(
    file_path: str,
    library_name: str,
    video_codec: str,
    resolution_h: int,
    file_size: int,
    mtime: float,
    bitrate_kbps: int = 0,
    container: str = "",
    audio_codec: str = "",
    audio_channels: int = 0,
    duration: float = 0,
) -> None:
    db = get_db()
    await db.execute(
        """INSERT OR REPLACE INTO library_files
           (file_path, library_name, video_codec, resolution_h, file_size, mtime,
            bitrate_kbps, container, audio_codec, audio_channels, duration)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            file_path,
            library_name,
            video_codec,
            resolution_h,
            file_size,
            mtime,
            bitrate_kbps,
            container,
            audio_codec,
            audio_channels,
            duration,
        ),
    )
    await db.commit()


async def remove_library_file(file_path: str, library_name: str) -> None:
    db = get_db()
    await db.execute(
        "DELETE FROM library_files WHERE file_path = ? AND library_name = ?",
        (file_path, library_name),
    )
    await db.commit()


async def find_rename_candidate(
    new_path: str, library_name: str, file_size: int
) -> str | None:
    conn = get_db()
    cursor = await conn.execute(
        "SELECT file_path FROM library_files WHERE library_name = ? AND file_size = ? AND file_path != ?",
        (library_name, file_size, new_path),
    )
    for row in await cursor.fetchall():
        if not Path(row[0]).exists():
            return row[0]
    return None


async def rename_file(
    old_path: str, new_path: str, library_name: str, new_mtime: float
) -> bool:
    db = get_db()
    updated = False
    for table in ("library_files", "processed_files"):
        # scan_library upserts the new path before rename detection runs
        await db.execute(
            f"DELETE FROM {table} WHERE file_path = ? AND library_name = ?",
            (new_path, library_name),
        )
        cursor = await db.execute(
            f"UPDATE {table} SET file_path = ? WHERE file_path = ? AND library_name = ?",
            (new_path, old_path, library_name),
        )
        if cursor.rowcount:
            updated = True
    if updated:
        await db.execute(
            "UPDATE library_files SET mtime = ? WHERE file_path = ? AND library_name = ?",
            (new_mtime, new_path, library_name),
        )
        await db.execute(
            "UPDATE processed_files SET mtime = ? WHERE file_path = ? AND library_name = ?",
            (new_mtime, new_path, library_name),
        )
    await db.commit()
    return updated


async def rename_library(old_name: str, new_name: str) -> None:
    db = get_db()
    for table in ("library_files", "processed_files", "job_history"):
        await db.execute(
            f"UPDATE {table} SET library_name = ? WHERE library_name = ?",
            (new_name, old_name),
        )
    await db.commit()


async def remove_library_files(library_name: str) -> None:
    db = get_db()
    await db.execute(
        "DELETE FROM library_files WHERE library_name = ?",
        (library_name,),
    )
    await db.commit()


async def cleanup_library_files(library_name: str, valid_paths: set[str]) -> None:
    db = get_db()
    cursor = await db.execute(
        "SELECT file_path FROM library_files WHERE library_name = ?",
        (library_name,),
    )
    rows = await cursor.fetchall()
    stale = [row[0] for row in rows if row[0] not in valid_paths]
    if stale:
        placeholders = ",".join("?" for _ in stale)
        await db.execute(
            f"DELETE FROM library_files WHERE library_name = ? AND file_path IN ({placeholders})",
            [library_name, *stale],
        )
        await db.commit()


async def get_library_files_mtimes(library_name: str) -> dict[str, float]:
    db = get_db()
    cursor = await db.execute(
        "SELECT file_path, mtime FROM library_files WHERE library_name = ?",
        (library_name,),
    )
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


# Stats queries


async def get_stats_totals() -> dict:
    db = get_db()
    cursor = await db.execute("""
        SELECT
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status IN ('skipped', 'skipped (rule)') THEN 1 ELSE 0 END) AS skipped,
            SUM(CASE WHEN status = 'completed' AND new_size_bytes IS NOT NULL
                THEN old_size_bytes - new_size_bytes ELSE 0 END) AS space_saved_bytes,
            SUM(CASE WHEN status = 'completed' THEN old_size_bytes ELSE 0 END) AS original_bytes,
            SUM(CASE WHEN status = 'completed' THEN duration_seconds ELSE 0 END) AS processing_seconds
        FROM job_history
        WHERE dismissed = 0
    """)
    row = await cursor.fetchone()
    return {
        "completed": row[0] or 0,
        "failed": row[1] or 0,
        "skipped": row[2] or 0,
        "space_saved_bytes": row[3] or 0,
        "original_bytes": row[4] or 0,
        "processing_seconds": row[5] or 0.0,
    }


async def get_stats_daily() -> list[dict]:
    db = get_db()
    cursor = await db.execute("""
        SELECT
            DATE(finished_at) AS date,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status = 'completed' AND new_size_bytes IS NOT NULL
                THEN old_size_bytes - new_size_bytes ELSE 0 END) AS space_saved_bytes
        FROM job_history
        WHERE dismissed = 0
        GROUP BY DATE(finished_at)
        ORDER BY date
    """)
    rows = await cursor.fetchall()
    return [
        {
            "date": r[0],
            "completed": r[1],
            "failed": r[2],
            "space_saved_bytes": r[3] or 0,
        }
        for r in rows
    ]


async def get_stats_by_library() -> list[dict]:
    db = get_db()
    cursor = await db.execute("""
        SELECT
            library_name,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status IN ('completed', 'skipped', 'skipped (rule)', 'cancelled') THEN 1 ELSE 0 END) AS processed,
            SUM(CASE WHEN status IN ('skipped', 'skipped (rule)') THEN 1 ELSE 0 END) AS skipped,
            SUM(CASE WHEN status = 'completed' AND new_size_bytes IS NOT NULL
                THEN old_size_bytes - new_size_bytes ELSE 0 END) AS space_saved_bytes,
            SUM(CASE WHEN status = 'completed' THEN old_size_bytes ELSE 0 END) AS original_bytes
        FROM job_history
        WHERE dismissed = 0
        GROUP BY library_name
    """)
    rows = await cursor.fetchall()
    return [
        {
            "library": r[0],
            "completed": r[1],
            "failed": r[2],
            "processed": r[3],
            "skipped": r[4] or 0,
            "space_saved_bytes": r[5] or 0,
            "original_bytes": r[6] or 0,
        }
        for r in rows
    ]


async def get_stats_top_savings(limit: int = 10) -> list[dict]:
    db = get_db()
    cursor = await db.execute(
        """
        SELECT file_path, old_size_bytes, new_size_bytes, library_name
        FROM job_history
        WHERE status = 'completed' AND new_size_bytes IS NOT NULL AND dismissed = 0
        ORDER BY CAST(new_size_bytes AS REAL) / old_size_bytes ASC
        LIMIT ?
    """,
        (limit,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "file_path": r[0],
            "old_size_bytes": r[1],
            "new_size_bytes": r[2],
            "library_name": r[3],
        }
        for r in rows
    ]


async def get_stats_by_device() -> list[dict]:
    db = get_db()
    cursor = await db.execute("""
        SELECT
            device_name,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'completed' THEN duration_seconds ELSE 0 END) AS processing_seconds
        FROM job_history
        WHERE device_name != '' AND dismissed = 0
        GROUP BY device_name
    """)
    rows = await cursor.fetchall()
    return [
        {
            "device": r[0],
            "completed": r[1],
            "processing_seconds": r[2] or 0.0,
        }
        for r in rows
    ]


async def get_stats_composition() -> dict[str, dict[str, int]]:
    db = get_db()
    cursor = await db.execute("""
        SELECT library_name, video_codec, COUNT(*) AS cnt
        FROM library_files
        WHERE video_codec != ''
        GROUP BY library_name, video_codec
    """)
    rows = await cursor.fetchall()
    result: dict[str, dict[str, int]] = {}
    for r in rows:
        lib = r[0]
        if lib not in result:
            result[lib] = {}
        result[lib][r[1]] = r[2]
    return result


async def get_stats_file_counts() -> dict[str, int]:
    db = get_db()
    cursor = await db.execute("""
        SELECT library_name, COUNT(*) AS cnt
        FROM library_files
        GROUP BY library_name
    """)
    rows = await cursor.fetchall()
    return {r[0]: r[1] for r in rows}


async def get_stats_processed_counts() -> dict[str, int]:
    db = get_db()
    cursor = await db.execute("""
        SELECT lf.library_name, COUNT(*) AS cnt
        FROM library_files lf
        INNER JOIN processed_files pf
            ON lf.file_path = pf.file_path AND lf.library_name = pf.library_name
        GROUP BY lf.library_name
    """)
    rows = await cursor.fetchall()
    return {r[0]: r[1] for r in rows}
