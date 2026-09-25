_UNITS = ("KB", "MB", "GB", "TB")


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    value = size_bytes
    for unit in _UNITS:
        value /= 1024
        # Checks the rounded value, or 1023.96 MB would print as 1024.0 MB
        if round(value, 1) < 1024 or unit == _UNITS[-1]:
            return f"{value:.1f} {unit}"
