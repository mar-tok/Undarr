import logging
from logging.handlers import RotatingFileHandler

import config

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
        config.LOG_DIR / "undarr.log",
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

log = get_logger()