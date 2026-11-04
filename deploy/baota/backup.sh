#!/usr/bin/env bash
# 每日备份 SpoilerShield 的 SQLite 与上传文件。
#
# 宝塔：计划任务 → 添加任务 → Shell 脚本，每天 03:20 执行：
#   bash /www/wwwroot/textadventure.top/deploy/baota/backup.sh
#
# 建议再把 /www/backup/spoilershield 同步到腾讯云 COS 或另一台机器。

set -euo pipefail

APP=/www/wwwroot/textadventure.top
DATA="$APP/data"
DEST=/www/backup/spoilershield
KEEP_DAYS=14
STAMP=$(date +%F-%H%M)

mkdir -p "$DEST"

# SQLite 在线备份：不要直接 cp 正在写入的数据库文件。
"$APP/.venv/bin/python" - "$DATA/spoiler_shield.db" "$DEST/db-$STAMP.db" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
with target:
    source.backup(target)
target.close()
source.close()
PY

tar czf "$DEST/uploads-$STAMP.tar.gz" -C "$DATA" uploads
find "$DEST" -type f -mtime +"$KEEP_DAYS" -delete

echo "[$(date '+%F %T')] backup ok: $DEST/db-$STAMP.db, $DEST/uploads-$STAMP.tar.gz"
