# Deployment to OVHCloud VPS

Complete guide for deploying the notification-bot to OVHCloud VPS with Docker and GitHub Actions.

## Prerequisites

- OVHCloud VPS with Docker and docker-compose installed
- Git repository on GitHub
- SSH key for accessing VPS

## 1. Initial VPS Setup

### 1.1 Connect to VPS
```bash
ssh root@<VPS_IP>
```

### 1.2 Create project directory
```bash
mkdir -p /path/to/notification-bot
cd /path/to/notification-bot

# Initialize git (if not cloned)
git init
git remote add origin https://github.com/your-username/notification-bot.git
git fetch origin
git checkout main
```

### 1.3 Verify existing containers don't conflict
```bash
docker ps
docker network ls

# Ensure 'bot-network' doesn't already exist (or update docker-compose.yml)
```

### 1.4 Test Doppler access
```bash
doppler login
doppler projects
doppler secrets --project notifications-bot --config dev
```

### 1.5 First deployment (manual)
```bash
cd /path/to/notification-bot

# Build and start
docker-compose build
docker-compose up -d

# Verify
docker-compose ps
docker logs -f notification-bot
```

## 2. GitHub Actions Setup

### 2.1 Add SSH Key to GitHub Secrets
```bash
# On your local machine, generate or use existing SSH key
cat ~/.ssh/id_rsa  # (or your key path)

# Copy the output and add to GitHub:
# 1. Go to: Settings → Secrets and variables → Actions
# 2. Click "New repository secret"
# 3. Name: VPS_SSH_KEY
# 4. Value: [paste your private SSH key]
```

### 2.2 Add VPS Host and User to GitHub Secrets
```bash
# In the same GitHub Secrets page, add:
# - VPS_HOST: <your-vps-ip-or-domain>
# - VPS_USER: root (or your deployment user)
```

### 2.3 Update deploy.yml paths
Edit `.github/workflows/deploy.yml` and replace `/path/to/notification-bot` with your actual VPS path:

```yaml
script: |
  cd /home/ubuntu/notification-bot  # or wherever you cloned it
  git pull origin main
  docker-compose down
  docker-compose build --no-cache
  docker-compose up -d
```

### 2.4 Test the workflow
```bash
# Push a commit to main
git add .
git commit -m "test deploy"
git push origin main

# Check GitHub Actions:
# 1. Go to: Actions tab
# 2. Wait for workflow to complete
# 3. Click on the run to see logs
```

## 3. Manual Deployment (without GitHub Actions)

```bash
# Option 1: Use deploy.sh script
chmod +x scripts/deploy.sh
./scripts/deploy.sh <VPS_IP> root

# Option 2: SSH directly
ssh root@<VPS_IP> << 'EOF'
  cd /path/to/notification-bot
  git pull origin main
  docker-compose build
  docker-compose up -d
  docker logs -f notification-bot --tail 20
EOF
```

## 4. Logging & Monitoring

### 4.1 View logs in real-time
```bash
# Docker logs (JSON format + stdout)
docker logs -f notification-bot

# Log file (inside container)
docker exec notification-bot tail -f /app/logs/log.log
```

### 4.2 Copy logs from VPS to local
```bash
# Download entire logs directory
scp -r root@<VPS_IP>:/path/to/notification-bot/logs ./logs_backup

# Or just latest log
scp root@<VPS_IP>:/path/to/notification-bot/logs/log.log ./latest.log
```

### 4.3 Verify bot is alive
```bash
# Send /ping command to your bot on Telegram
# You should get: 🏓 pong

# Or check container status
docker ps | grep notification-bot
```

## 5. Managing Other Containers

### 5.1 Network isolation
The bot uses `bot-network` (Docker bridge network). This is isolated from other containers by default.

```bash
# Verify no conflicts
docker network inspect bot-network

# If needed, update docker-compose.yml to use a different network name
# and update all container references
```

### 5.2 Port mapping
By default, notification-bot doesn't expose ports (Telegram bot via polling).

If you need to add API endpoints, update docker-compose.yml:
```yaml
services:
  notification-bot:
    ports:
      - "8000:8000"  # Only if needed
```

### 5.3 Ensure no service interference
```bash
# Check Docker disk usage
docker system df

# Check running containers
docker ps -a

# If cleanup needed
docker system prune -a --volumes  # WARNING: removes unused resources
```

## 6. Troubleshooting

### Container won't start
```bash
# Check logs
docker logs notification-bot

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Doppler access denied
```bash
# Re-authenticate
docker exec notification-bot doppler login
docker-compose restart
```

### Logs not writing to log.log
```bash
# Verify /app/logs exists and is writable
docker exec notification-bot ls -la /app/logs

# Check file permissions
docker exec notification-bot ls -la /app/logs/log.log
```

### restart: always not working
```bash
# Verify docker daemon is running
systemctl status docker

# Restart docker daemon
systemctl restart docker

# Verify container restarts
docker-compose up -d
docker ps  # Should show notification-bot with "Restarting" or "Up"
```

## 7. Rollback to Previous Version

```bash
# View git history
git log --oneline

# Revert to specific commit
git revert <commit-hash>
# or
git reset --hard <commit-hash>

# Redeploy
git push origin main
# (GitHub Actions will trigger automatically, or manual deploy)
```

## 8. Environment Variables in Docker

If Doppler is unavailable, use environment variables:

```bash
# Create .env file (DO NOT commit)
echo "TELEGRAM_BOT_TOKEN=..." > /path/to/notification-bot/.env
echo "TELEGRAM_CHAT_ID=..." >> /path/to/notification-bot/.env
echo "OPENAI_API_KEY=..." >> /path/to/notification-bot/.env

# Update docker-compose.yml
services:
  notification-bot:
    env_file: .env
```

**WARNING**: Never commit `.env` to git!

## 9. Health Checks

Add health check to docker-compose.yml:

```yaml
services:
  notification-bot:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"] || exit 1
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

(Requires exposing a health endpoint in the bot code)

## 10. Monitoring & Alerts

### Option 1: Check logs periodically
```bash
# From local machine
ssh root@<VPS_IP> docker logs notification-bot | tail -100
```

### Option 2: Set up Telegram alerts (future)
Modify scheduler to send alert if bot hasn't processed tasks in N hours.

### Option 3: External monitoring
- Use Telegram @BotFather to set webhook for alerts
- Set up cron job to check bot health via /ping

## Quick Reference

| Task | Command |
|------|---------|
| Deploy | `./scripts/deploy.sh <IP>` or push to main (auto via GitHub Actions) |
| View logs | `docker logs -f notification-bot` |
| Restart bot | `docker-compose restart notification-bot` |
| Stop bot | `docker-compose down` |
| Check status | `docker ps \| grep notification-bot` |
| SSH to VPS | `ssh root@<VPS_IP>` |
| Connect to container | `docker exec -it notification-bot bash` |

---

**Last Updated**: May 2026  
**Tested with**: OVHCloud VPS, Docker 24.0+, docker-compose 2.20+
