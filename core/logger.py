import logging
import re
from logging.handlers import RotatingFileHandler

import config

LOG_FILE = config.LOG_DIR / "undarr.log"
LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}

# Must match the formatter in get_logger
_ENTRY_RE = re.compile(r"\d{4}-\d{2}-\d{2} \S+ +(\w+)")

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    _logger = logging.getLogger("undarr")
    _logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s - %(message)s")

    fh = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    _logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    _logger.addHandler(sh)

    return _logger


def filter_level(lines: list[str], level: str) -> list[str]:
    threshold = LEVEL_RANK[level]
    kept = []
    # Traceback lines have no level and take the last entry's
    keep = False
    for ln in lines:
        m = _ENTRY_RE.match(ln)
        if m and m.group(1) in LEVEL_RANK:
            keep = LEVEL_RANK[m.group(1)] >= threshold
        if keep:
            kept.append(ln)
    return kept


log = get_logger()
