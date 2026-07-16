from __future__ import annotations

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


async def has_completed_job(file_path: str) -> bool:
    db = get_db()
    row = await db.execute_fetchall(
        "SELECT 1 FROM job_history WHERE file_path = ? AND status = 'completed' LIMIT 1",
        (file_path,),
    )
    return len(row) > 0


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
    preset_name: str = "",
    device_name: str = "",
) -> None:
    db = get_db()
    await db.execute(
        """INSERT INTO job_history
           (id, library_name, file_path, status, old_size_bytes, new_size_bytes,
            started_at, finished_at, duration_seconds, ffmpeg_log, error_message,
            preset_name, device_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
}


async def get_history(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
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
