#!/bin/bash

# OVHCloud VPS Deployment Script
# Usage: ./scripts/deploy.sh <host> <user>
# Example: ./scripts/deploy.sh 123.45.67.89 root

set -e

VPS_HOST=${1:-""}
VPS_USER=${2:-"root"}
BOT_DIR="/path/to/notification-bot"

if [ -z "$VPS_HOST" ]; then
    echo "Usage: ./scripts/deploy.sh <host> [user]"
    echo "Example: ./scripts/deploy.sh 123.45.67.89 root"
    exit 1
fi

echo "🚀 Deploying to $VPS_USER@$VPS_HOST:$BOT_DIR"

ssh "$VPS_USER@$VPS_HOST" << 'EOF'
    set -e

    echo "📍 Current directory: $(pwd)"
    cd /path/to/notification-bot || exit 1

    echo "📥 Pulling latest code..."
    git pull origin main

    echo "🔨 Building Docker image..."
    docker-compose build --no-cache

    echo "🛑 Stopping old container..."
    docker-compose down || true

    echo "🚀 Starting new container..."
    docker-compose up -d

    echo "✅ Deployment complete!"
    echo ""
    echo "📋 Container status:"
    docker-compose ps

    echo ""
    echo "📜 Last 20 logs:"
    docker logs -f notification-bot --tail 20 &
    sleep 3
    pkill -f "docker logs" || true
EOF

echo "✨ Deployment successful!"
