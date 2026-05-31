#!/bin/bash
# Start Der Tippmeister container — PRODUCTION ONLY (not bastion)
set -e

if [[ "$(hostname)" == bastion* ]]; then
	echo "ERROR: This app must NOT run on bastion. Deploy to production host only."
	exit 1
fi

IMAGE_NAME="${IMAGE_NAME:-tippmeister}"
CONTAINER_NAME="${CONTAINER_NAME:-tippmeister}"
PORT="${PORT:-9443}"

# --- Load configuration from ~/.tm.conf ---
TM_CONF="${TM_CONF:-$HOME/.tm.conf}"
if [ -f "$TM_CONF" ]; then
	. "$TM_CONF"
else
	echo "ERROR: Config file not found: $TM_CONF"
	echo "Create it with: ADMIN_EMAILS, INVITE_TOKEN, GMAIL_USER, GMAIL_APP_PASSWORD, SITE_URL"
	exit 1
fi

# Build if image doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
	echo "Building $IMAGE_NAME image..."
	podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

# Stop existing container if running
if podman container exists "$CONTAINER_NAME" 2>/dev/null; then
	echo "Stopping existing container..."
	podman stop -t 2 "$CONTAINER_NAME" || true
	podman rm "$CONTAINER_NAME" || true
fi

HTTP_PORT="${HTTP_PORT:-8080}"

echo "Starting $CONTAINER_NAME on port $PORT (HTTPS) + $HTTP_PORT (HTTP redirect)..."
podman run -d \
	--name "$CONTAINER_NAME" \
	-p "${PORT}:${PORT}" \
	-p "${HTTP_PORT}:8080" \
	-v tippmeister-data:/data:Z \
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
echo "Der Tippmeister is running!"
echo "  HTTPS: https://$(hostname):$PORT"
echo "  HTTP:  http://$(hostname):$HTTP_PORT (redirects to HTTPS)"
echo "  Logs: podman logs -f $CONTAINER_NAME"

# Show invite token from logs
sleep 2
podman logs "$CONTAINER_NAME" 2>&1 | grep -i "invite" || true
