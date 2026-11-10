#!/bin/bash
# Runs everything in one container: web, background worker (+ scheduler) and
# the consume-folder watcher. No Redis, no external database (SQLite in /data).
set -euo pipefail

mkdir -p "$PAPERLESS_DATA_DIR/queue/broker" "$PAPERLESS_DATA_DIR/queue/control" \
         "$PAPERLESS_DATA_DIR/queue/results" "$PAPERLESS_DATA_DIR/log" \
         "$PAPERLESS_MEDIA_ROOT" "$PAPERLESS_CONSUMPTION_DIR"

# Generate and keep a secret key if none is supplied.
if [ -z "${PAPERLESS_SECRET_KEY:-}" ]; then
  KEYFILE="$PAPERLESS_DATA_DIR/secret.key"
  [ -s "$KEYFILE" ] || (umask 077; python -c "import secrets;print(secrets.token_urlsafe(64))" > "$KEYFILE")
  export PAPERLESS_SECRET_KEY="$(cat "$KEYFILE")"
fi

# Stale queue entries from an unclean shutdown must not block startup.
rm -rf "$PAPERLESS_DATA_DIR/queue/control"/* 2>/dev/null || true

python manage.py migrate --noinput

# Optional: create/reset an admin from the environment. Otherwise the web UI
# asks for the first account on first visit.
if [ -n "${PAPERLESS_ADMIN_USER:-}" ] && [ -n "${PAPERLESS_ADMIN_PASSWORD:-}" ]; then
  python manage.py manage_superuser || true
fi

pids=()
celery -A paperless worker --beat -l warning --concurrency="${PAPERLESS_TASK_WORKERS:-1}" &
pids+=($!)
python manage.py document_consumer &
pids+=($!)
granian --interface wsgi --host 0.0.0.0 --port 8000 \
        --workers "${PAPERLESS_WEBSERVER_WORKERS:-1}" paperless.wsgi:application &
pids+=($!)

trap 'kill "${pids[@]}" 2>/dev/null || true' TERM INT
# If any process dies the container exits and the restart policy brings it back.
wait -n
kill "${pids[@]}" 2>/dev/null || true
exit 1
