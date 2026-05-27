#!/bin/bash
# Generate a self-signed TLS certificate for Der Tippmeister
set -e

CERT_DIR="${1:-/data/certs}"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
	echo "Certificates already exist in $CERT_DIR, skipping generation."
	exit 0
fi

echo "Generating self-signed TLS certificate..."
openssl req -x509 -newkey rsa:2048 \
	-keyout "$CERT_DIR/key.pem" \
	-out "$CERT_DIR/cert.pem" \
	-days 365 \
	-nodes \
	-subj "/CN=tippmeister/O=DerTippmeister/C=DE" \
	-addext "subjectAltName=DNS:localhost,DNS:tippmeister,DNS:bastion,IP:127.0.0.1"

echo "Certificate generated:"
echo "  $CERT_DIR/cert.pem"
echo "  $CERT_DIR/key.pem"
