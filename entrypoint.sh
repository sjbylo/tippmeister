#!/bin/bash
set -e

# Generate self-signed cert if not present
bash /app/generate-cert.sh /data/certs

PORT="${PORT:-9443}"

echo "=== Der Tippmeister ==="
echo "Starting on port $PORT (HTTPS) + 8080 (HTTP redirect)"
echo "Invite token: ${INVITE_TOKEN:-check logs}"
echo "========================"

# HTTP->HTTPS redirect on port 8080 (background)
python /app/http_redirect.py &

exec gunicorn wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --certfile /data/certs/cert.pem \
    --keyfile /data/certs/key.pem \
    --workers 2 \
    --preload \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
