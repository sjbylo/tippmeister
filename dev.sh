#!/bin/bash
# Dev mode: mount source code into container, skip rebuild.
# Code changes take effect with: podman restart tippmeister
set -e

IMAGE_NAME="${IMAGE_NAME:-tippmeister}"
CONTAINER_NAME="${CONTAINER_NAME:-tippmeister}"
PORT="${PORT:-9443}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

TM_CONF="${TM_CONF:-$HOME/.tm.conf}"
if [ -f "$TM_CONF" ]; then
	. "$TM_CONF"
else
	echo "ERROR: Config file not found: $TM_CONF"
	exit 1
fi

# Build only if image doesn't exist yet
if ! podman image exists "$IMAGE_NAME"; then
	echo "First run -- building $IMAGE_NAME image..."
	podman build -t "$IMAGE_NAME" "$SCRIPT_DIR"
fi

# Stop existing container
if podman container exists "$CONTAINER_NAME" 2>/dev/null; then
	podman stop "$CONTAINER_NAME" 2>/dev/null || true
	podman rm "$CONTAINER_NAME" 2>/dev/null || true
fi

HTTP_PORT="${HTTP_PORT:-8080}"

VOLDIR=$(podman volume inspect tippmeister-data --format '{{.Mountpoint}}' 2>/dev/null) || true
if [ -n "$VOLDIR" ] && [ -d "$VOLDIR" ]; then
	chmod 777 "$VOLDIR"
	[ -f "$VOLDIR/tippmeister.db" ] && chmod 666 "$VOLDIR/tippmeister.db"
	[ -f "$VOLDIR/.secret_key" ] && chmod 666 "$VOLDIR/.secret_key"
	[ -d "$VOLDIR/certs" ] && chmod 755 "$VOLDIR/certs" && chmod 644 "$VOLDIR/certs/"*.pem 2>/dev/null || true
fi

echo "Starting $CONTAINER_NAME (DEV mode -- source mounted from $SCRIPT_DIR)..."
podman run -d \
	--name "$CONTAINER_NAME" \
	-p "${PORT}:${PORT}" \
	-p "${HTTP_PORT}:8080" \
	-v tippmeister-data:/data \
	-v "$SCRIPT_DIR/app":/app/app:ro,Z \
	-v "$SCRIPT_DIR/translations":/app/translations:ro,Z \
	-v "$SCRIPT_DIR/data":/app/data:ro,Z \
	-v "$SCRIPT_DIR/config.py":/app/config.py:ro,Z \
	-v "$SCRIPT_DIR/wsgi.py":/app/wsgi.py:ro,Z \
	-v "$SCRIPT_DIR/http_redirect.py":/app/http_redirect.py:ro,Z \
	-v "$SCRIPT_DIR/tls_proxy.py":/app/tls_proxy.py:ro,Z \
	-e PORT="$PORT" \
	-e SECRET_KEY="${SECRET_KEY:-}" \
	-e INVITE_TOKEN="${INVITE_TOKEN:-}" \
	-e ADMIN_EMAILS="${ADMIN_EMAILS:-}" \
	-e API_FOOTBALL_KEY="${API_FOOTBALL_KEY:-}" \
	-e GMAIL_USER="${GMAIL_USER:-}" \
	-e GMAIL_APP_PASSWORD="${GMAIL_APP_PASSWORD:-}" \
	-e GMAIL_FROM="${GMAIL_FROM:-}" \
	-e SITE_URL="${SITE_URL:-}" \
	"$IMAGE_NAME"

echo ""
echo "Der Tippmeister is running (DEV mode)!"
echo "  HTTPS: https://$(hostname):$PORT"
echo "  Code changes: podman restart $CONTAINER_NAME"
echo "  Logs: podman logs -f $CONTAINER_NAME"

sleep 2
podman logs "$CONTAINER_NAME" 2>&1 | grep -i "invite" || true
