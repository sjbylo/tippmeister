#!/bin/bash
# Stop Der Tippmeister container
set -e

CONTAINER_NAME="${CONTAINER_NAME:-tippmeister}"

if podman container exists "$CONTAINER_NAME" 2>/dev/null; then
	echo "Stopping $CONTAINER_NAME..."
	podman stop "$CONTAINER_NAME"
	podman rm "$CONTAINER_NAME"
	echo "Stopped."
else
	echo "$CONTAINER_NAME is not running."
fi
