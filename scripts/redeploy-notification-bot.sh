#!/usr/bin/env bash
# Redeploy script for notification-bot on VPS
# Place this in /opt/redeploy-notification-bot.sh on your VPS
# Called by GitHub Actions after Docker image is pushed to Docker Hub
#
# Проект вынесен в собственный Compose-проект /srv/notification-bot (name: notification-bot),
# чтобы деплой не мог задеть контейнеры других проектов — в частности radio-encoder.
# Не возвращать сюда --force-recreate и --remove-orphans: на общем проекте они сносили чужое.

set -euo pipefail

cd /srv/notification-bot
C=notification-bot-notification-bot-1

docker compose pull notification-bot
docker compose up -d --no-deps notification-bot

echo "Waiting for healthcheck..."
for i in {1..20}; do
  if curl -fsS http://127.0.0.1:8002/health >/dev/null; then
    echo "notification-bot is healthy"
    docker ps --filter "name=$C" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    docker logs --tail=50 "$C"
    exit 0
  fi

  echo "not ready yet, attempt $i/20"
  docker ps -a --filter "name=$C" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
  sleep 2
done

echo "notification-bot failed healthcheck"
docker ps -a --filter "name=$C" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs --tail=120 "$C" || true
exit 1
