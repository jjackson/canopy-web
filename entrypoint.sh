#!/bin/bash
# Persist Claude CLI auth across container rebuilds.
# Symlinks /root/.claude and /root/.claude.json to a Docker volume.

PERSIST_DIR=/root/claude-data

mkdir -p "$PERSIST_DIR/.claude"

# Symlink .claude directory
if [ ! -L /root/.claude ]; then
    rm -rf /root/.claude
    ln -s "$PERSIST_DIR/.claude" /root/.claude
fi

# Symlink .claude.json
if [ -f "$PERSIST_DIR/.claude.json" ]; then
    ln -sf "$PERSIST_DIR/.claude.json" /root/.claude.json
elif [ -f /root/.claude.json ] && [ ! -L /root/.claude.json ]; then
    # First run — move existing file into volume
    mv /root/.claude.json "$PERSIST_DIR/.claude.json"
    ln -s "$PERSIST_DIR/.claude.json" /root/.claude.json
else
    # No file yet — create empty one in volume and symlink
    echo '{}' > "$PERSIST_DIR/.claude.json"
    ln -sf "$PERSIST_DIR/.claude.json" /root/.claude.json
fi

exec "$@"
