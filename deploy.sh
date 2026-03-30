#!/bin/bash
set -e

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/can-we-update-mc}"

if [ -z "$REMOTE_HOST" ]; then
    echo "Error: REMOTE_HOST not set"
    echo "Usage: REMOTE_HOST=server.example.com ./deploy.sh"
    exit 1
fi

echo "Building Docker image..."
docker build -t can-we-update-mc:latest .

echo "Tagging image..."
docker tag can-we-update-mc:latest can-we-update-mc:deploy

echo "Saving image to archive..."
docker save can-we-update-mc:deploy -o /tmp/can-we-update-mc.tar

echo "Transferring to $REMOTE_USER@$REMOTE_HOST..."
scp /tmp/can-we-update-mc.tar "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo "Loading and restarting on remote..."
ssh "$REMOTE_USER@$REMOTE_HOST" << 'EOF'
    cd /opt/can-we-update-mc
    docker load -i can-we-update-mc.tar
    docker-compose up -d --build
    rm -f can-we-update-mc.tar
EOF

rm /tmp/can-we-update-mc.tar
echo "Deployment complete!"
