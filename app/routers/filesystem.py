from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])

SYSTEM_FS_TYPES = frozenset(
    {
        "overlay",
        "proc",
        "sysfs",
        "cgroup",
        "cgroup2",
        "tmpfs",
        "devpts",
        "devtmpfs",
        "mqueue",
        "hugetlbfs",
        "securityfs",
        "pstore",
        "debugfs",
        "tracefs",
        "fusectl",
        "configfs",
        "binfmt_misc",
        "nsfs",
        "autofs",
        "efivarfs",
        "bpf",
        "ramfs",
    }
)

HIDDEN_PATH_PREFIXES = (
    "/app",
    "/data",
    "/logs",
    "/dev",
    "/etc",
    "/run",
    "/var",
    "/sys",
    "/proc",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/boot",
    "/root",
    "/opt",
)


def _get_user_roots() -> list[dict]:
    try:
        text = Path("/proc/mounts").read_text()
    except OSError:
        return []

    seen = set()
    mount_points = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount_point, fs_type = parts[1], parts[2]
        if fs_type in SYSTEM_FS_TYPES:
            continue
        if mount_point in seen:
            continue
        seen.add(mount_point)
        if mount_point == "/":
            continue
        if mount_point.startswith(HIDDEN_PATH_PREFIXES):
            continue
        if not Path(mount_point).is_dir():
            continue
        mount_points.append(mount_point)

    # Drop child mounts whose parent is already in the list
    mount_set = set(mount_points)
    roots = []
    for mp in mount_points:
        parent = mp.rsplit("/", 1)[0]
        while parent and parent != "/":
            if parent in mount_set:
                break
            parent = parent.rsplit("/", 1)[0]
        else:
            name = mp.rstrip("/").rsplit("/", 1)[-1]
            roots.append({"name": name, "path": mp})

    return roots


@router.get("/roots")
async def list_roots():
    return _get_user_roots()


@router.get("/browse")
async def browse_directory(path: str):
    if not path.startswith("/"):
        raise HTTPException(400, "Path must be absolute")

    # Resolve to a canonical path before checking against the blocklist,
    # so that ".." segments cannot bypass the prefix check.
    p = Path(path).resolve()
    resolved = str(p)

    if resolved == "/" or resolved.startswith(HIDDEN_PATH_PREFIXES):
        raise HTTPException(403, "Path is not browsable")

    if not p.exists():
        raise HTTPException(404, "Path not found")
    if not p.is_dir():
        raise HTTPException(400, "Path is not a folder")

    try:
        entries = sorted(
            [
                {"name": child.name, "path": str(child)}
                for child in p.iterdir()
                if child.is_dir() and not child.name.startswith(".")
            ],
            key=lambda e: e["name"].lower(),
        )
    except PermissionError:
        raise HTTPException(403, "Permission denied")

    parent = str(p.parent) if str(p) != "/" else None
    return {"path": str(p), "parent": parent, "entries": entries}
