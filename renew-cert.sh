#!/bin/bash
# Renew or obtain Let's Encrypt certificate for Der Tippmeister
# Uses DNS-01 challenge (no need for port 80 to be open)
set -e

DOMAIN="${1:-game.bylo.de}"
EMAIL="${2:-stephenbylo@gmail.com}"
CONTAINER_NAME="tippmeister"
VOLUME_NAME="tippmeister-data"

echo "=== Let's Encrypt Certificate for $DOMAIN ==="
echo ""

# Step 1: Request/renew cert via DNS-01 challenge
echo "Requesting certificate via DNS-01 challenge..."
echo "You will be asked to create a TXT record in your DNS provider (ZoneEdit)."
echo ""
sudo certbot certonly --manual --preferred-challenges dns \
	-d "$DOMAIN" \
	--email "$EMAIL" \
	--agree-tos \
	--no-eff-email

# Step 2: Copy certs into Podman volume
VOLDIR=$(podman volume inspect "$VOLUME_NAME" --format '{{.Mountpoint}}')
echo ""
echo "Copying certificates to container volume..."
mkdir -p "$VOLDIR/certs"
sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$VOLDIR/certs/cert.pem"
sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$VOLDIR/certs/key.pem"
# Container runs as non-root (uid 65532) and needs read access
chmod 644 "$VOLDIR/certs/cert.pem" "$VOLDIR/certs/key.pem"

# Step 3: Restart container
echo "Restarting $CONTAINER_NAME..."
podman restart "$CONTAINER_NAME" 2>/dev/null || echo "Container not running, start it with: bash start.sh.local"

echo ""
echo "Done! Verify with:"
echo "  curl -v https://$DOMAIN:9443 2>&1 | grep 'subject:'"
echo ""
echo "Certificate expires in 90 days. Re-run this script to renew."
