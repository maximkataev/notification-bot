#!/bin/bash

# Redeploy script for notification-bot on VPS
# Place this in /opt/redeploy-notification-bot.sh on your VPS
# Called by GitHub Actions after Docker image is pushed to Docker Hub

set -e

# Export variables for docker-compose
export DOCKER_HUB_USERNAME="${DOCKER_HUB_USERNAME}"
export NOTIFICATION_BOT_DOPPLER_TOKEN="${NOTIFICATION_BOT_DOPPLER_TOKEN}"

# Navigate to notification-bot directory
cd /opt/notification-bot || exit 1

echo "📦 Pulling latest Docker image..."
docker compose pull

echo "🚀 Starting notification-bot container..."
docker compose up -d --force-recreate --remove-orphans

echo "✅ Redeploy complete!"
echo ""
echo "📋 Container status:"
docker compose ps

echo ""
echo "📜 Recent logs:"
docker logs -f notification-bot --tail 10 &
sleep 2
pkill -f "docker logs" || true
