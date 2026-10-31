#!/bin/sh
set -eu
umask 077

backup_dir=${1:-./backups}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
database_name=$timestamp-database.dump
uploads_name=$timestamp-uploads.tar.gz
checksums_name=$timestamp-SHA256SUMS
destination=$(mkdir -p "$backup_dir" && cd "$backup_dir" && pwd)
chmod 700 "$destination"
stage=$(mktemp -d "$destination/.backup-$timestamp.XXXXXX")
web_was_running=false
scheduler_was_running=false

running_services=$(docker compose ps --status running --services)
case " $running_services " in
  *" web "*) web_was_running=true ;;
esac
case " $running_services " in
  *" scheduler "*) scheduler_was_running=true ;;
esac

if [ "$web_was_running" = true ] || [ "$scheduler_was_running" = true ]; then
  docker compose stop web scheduler
fi

cleanup() {
  result=$?
  rm -rf "$stage"
  if [ "$web_was_running" = true ]; then
    if ! docker compose start web; then
      printf 'Failed to restart the web service after backup.\n' >&2
      result=1
    fi
  fi
  if [ "$scheduler_was_running" = true ]; then
    if ! docker compose start scheduler; then
      printf 'Failed to restart the scheduler after backup.\n' >&2
      result=1
    fi
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

docker compose exec -T db sh -c \
  'exec pg_dump --format=custom --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$stage/$database_name"
docker compose run --rm --no-deps -T --entrypoint tar web -C /app -czf - uploads \
  > "$stage/$uploads_name"
(
  cd "$stage"
  sha256sum "$database_name" "$uploads_name" > "$checksums_name"
)
mv "$stage/$database_name" "$destination/$database_name"
mv "$stage/$uploads_name" "$destination/$uploads_name"
mv "$stage/$checksums_name" "$destination/$checksums_name"
rmdir "$stage"
printf 'Backup created: %s (%s)\n' "$destination" "$timestamp"
