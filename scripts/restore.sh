#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  printf 'Usage: %s DATABASE_DUMP UPLOADS_ARCHIVE\n' "$0" >&2
  exit 2
fi
database_dump=$1
uploads_archive=$2

if [ ! -f "$database_dump" ] || [ ! -f "$uploads_archive" ]; then
  printf 'Both backup files must exist.\n' >&2
  exit 2
fi
if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
  printf 'Restore replaces the current database contents. Set CONFIRM_RESTORE=yes to proceed.\n' >&2
  exit 2
fi

running_services=$(docker compose ps --status running --services)
case " $running_services " in
  *" web "*|*" scheduler "*)
    printf 'Stop web and scheduler services before restoring.\n' >&2
    exit 2
    ;;
esac

if [ -n "${BACKUP_CHECKSUMS:-}" ]; then
  (
    cd "$(dirname "$BACKUP_CHECKSUMS")"
    sha256sum --check "$(basename "$BACKUP_CHECKSUMS")"
  )
fi

docker compose exec -T db sh -c \
  'exec pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < "$database_dump"
docker compose run --rm --no-deps -T --entrypoint tar web -C /app -xzf - \
  < "$uploads_archive"
printf 'Restore completed. Review the application, then start services with docker compose up -d.\n'
