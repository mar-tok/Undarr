#!/bin/bash
set -e

PUID=${PUID:-911}
PGID=${PGID:-911}

groupmod -o -g "$PGID" undarr
usermod -o -u "$PUID" undarr

# /dev/dri keeps the host's GIDs
if [ -d /dev/dri ]; then
    for dev in /dev/dri/*; do
        gid=$(stat -c '%g' "$dev" 2>/dev/null) || continue
        [ "$gid" = "0" ] && continue
        groupadd -o -g "$gid" "devgid$gid" 2>/dev/null || true
        usermod -aG "devgid$gid" undarr 2>/dev/null || true
    done
fi

chown undarr:undarr /data /logs

exec gosu undarr "$@"
