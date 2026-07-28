#!/bin/sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${CONFIRM_RESTORE:?Set CONFIRM_RESTORE=YES to authorize database replacement}"

if [ "$CONFIRM_RESTORE" != "YES" ]; then
    printf 'Restore cancelled: CONFIRM_RESTORE must equal YES.\n' >&2
    exit 2
fi

source_dir="${1:?Usage: restore.sh <backup-directory>}"
attachment_root="${ATTACHMENT_STORAGE_DIR:-data/attachments}"
if [ ! -f "$source_dir/database.dump" ] \
    || [ ! -f "$source_dir/attachments.tar.gz" ] \
    || [ ! -f "$source_dir/checksums.sha256" ]; then
    printf 'Restore cancelled: backup files are incomplete.\n' >&2
    exit 2
fi

(
    cd "$source_dir"
    sha256sum -c checksums.sha256
)

if tar -tzf "$source_dir/attachments.tar.gz" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
    printf 'Restore cancelled: attachment archive contains unsafe paths.\n' >&2
    exit 2
fi

mkdir -p "$attachment_root"
if find "$attachment_root" -mindepth 1 -print -quit | grep -q .; then
    printf 'Restore cancelled: attachment destination must be empty.\n' >&2
    exit 2
fi

postgres_url="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
pg_restore \
    --dbname="$postgres_url" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    "$source_dir/database.dump"
tar -xzf "$source_dir/attachments.tar.gz" -C "$attachment_root"

printf 'Restore completed from: %s\n' "$source_dir"
