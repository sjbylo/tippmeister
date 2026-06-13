#!/bin/bash
# Start a local dev server on the bastion for testing UX changes.
# Uses a COPY of the production database — no risk to live app.
# Access at: http://bastion:5000

cd "$(dirname "$0")"

export FLASK_APP=wsgi.py
export FLASK_DEBUG=1
export SECRET_KEY="dev-secret-key-not-for-production"
export INVITE_TOKEN="dev-invite"
export ADMIN_EMAILS="admin@test.com"
export SITE_URL="http://localhost:5050"
export DATA_DIR="/home/steve/tippmeister/dev-instance"

echo "Starting dev server..."
echo "  URL: http://0.0.0.0:5050"
echo "  DB:  $DATA_DIR/tippmeister.db"
echo "  Press Ctrl+C to stop"
echo ""

python3 -m flask run --host=0.0.0.0 --port=5050
