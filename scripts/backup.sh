#!/bin/sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"

backup_root="${BACKUP_ROOT:-backups}"
attachment_root="${ATTACHMENT_STORAGE_DIR:-data/attachments}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${backup_root}/${timestamp}"
mkdir -p "$backup_root" "$attachment_root"
temporary="$(mktemp -d "${backup_root}/.backup-${timestamp}-XXXXXX")"
trap 'rm -rf -- "$temporary"' EXIT

postgres_url="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
pg_dump --dbname="$postgres_url" --format=custom --file="$temporary/database.dump"
tar -czf "$temporary/attachments.tar.gz" -C "$attachment_root" .
(
    cd "$temporary"
    sha256sum database.dump attachments.tar.gz > checksums.sha256
)
printf 'created_at=%s\n' "$timestamp" > "$temporary/manifest.txt"
mv "$temporary" "$target"
trap - EXIT

printf 'Backup created: %s\n' "$target"
