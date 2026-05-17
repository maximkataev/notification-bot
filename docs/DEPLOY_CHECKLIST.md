# OVHCloud Deployment Checklist

Complete this checklist to safely deploy the bot to OVHCloud VPS.

## Pre-Deployment (Local)

- [ ] Code is committed and pushed to main branch
- [ ] All tests pass locally
- [ ] Dockerfile builds without errors
- [ ] docker-compose.yml has correct paths
- [ ] .github/workflows/deploy.yml has correct VPS path
- [ ] Updated DEPLOY_OVHCLOUD.md with your VPS path

## VPS Setup

- [ ] Connected to VPS via SSH
- [ ] Verified Docker and docker-compose are installed
  ```bash
  docker --version
  docker-compose --version
  ```
- [ ] Created `/path/to/notification-bot` directory
- [ ] Cloned repository to VPS
- [ ] Verified no existing `bot-network` conflicts
- [ ] Tested Doppler access on VPS
  ```bash
  doppler login
  doppler secrets --project notifications-bot --config dev
  ```

## GitHub Actions Setup

- [ ] Generated/copied SSH private key
- [ ] Added `VPS_SSH_KEY` secret to GitHub
- [ ] Added `VPS_HOST` secret to GitHub (VPS IP or domain)
- [ ] Added `VPS_USER` secret to GitHub (usually `root`)
- [ ] Updated deploy.yml with correct project path
- [ ] Tested workflow by pushing commit to main
- [ ] Verified workflow succeeded in GitHub Actions tab

## Initial Deployment

- [ ] Ran first deployment manually on VPS
  ```bash
  cd /path/to/notification-bot
  docker-compose build
  docker-compose up -d
  ```
- [ ] Verified container is running
  ```bash
  docker-compose ps
  docker logs -f notification-bot --tail 20
  ```
- [ ] Tested bot connectivity
  - Sent `/ping` to bot → received `🏓 pong`
  - Sent `/info` to bot → received command list
- [ ] Verified logs are being written
  ```bash
  docker exec notification-bot tail -f /app/logs/log.log
  ```

## Docker Configuration

- [ ] restart: always is set in docker-compose.yml
- [ ] Volumes are correctly mounted (data, logs)
- [ ] Network name `bot-network` doesn't conflict with other containers
- [ ] Environment variables are correctly set (PYTHONUNBUFFERED=1, DOCKER_MODE=true)

## Doppler Integration

- [ ] TELEGRAM_BOT_TOKEN is set in Doppler
- [ ] TELEGRAM_CHAT_ID is set in Doppler
- [ ] OPENAI_API_KEY is set in Doppler
- [ ] TELEGRAM_USER_ID is set in Doppler (if multi-user)
- [ ] Doppler login works in container
  ```bash
  docker exec notification-bot doppler login
  ```

## Logging & Monitoring

- [ ] Logs directory exists and is writable
  ```bash
  docker exec notification-bot ls -la /app/logs
  ```
- [ ] log.log file is created
  ```bash
  docker exec notification-bot ls -la /app/logs/log.log
  ```
- [ ] Docker logs are viewable
  ```bash
  docker logs notification-bot
  ```
- [ ] Logs show JSON format (Docker) and readable format (file)

## Other Containers

- [ ] Listed all running containers
  ```bash
  docker ps
  ```
- [ ] Verified no port conflicts (bot uses polling, no exposed ports)
- [ ] Verified no network conflicts
  ```bash
  docker network ls
  ```
- [ ] Existing containers still function normally

## Post-Deployment Tests

- [ ] `/ping` command works → `🏓 pong`
- [ ] `/start` command works
- [ ] `/info` command shows all available commands
- [ ] `/debug` command shows user ID and chat ID
- [ ] Morning digest is scheduled (or test via `/digest`)
- [ ] News fetching works
- [ ] Task parsing works (send `/plan` command)
- [ ] Weather aggregation works
- [ ] Exchange rates are fetched
- [ ] No errors in logs
  ```bash
  docker logs notification-bot | grep -i error
  ```

## Continuous Deployment (GitHub Actions)

- [ ] Make a test commit (e.g., update README)
- [ ] Push to main
- [ ] Verify GitHub Actions workflow runs automatically
- [ ] Verify deployment completes successfully
- [ ] Verify bot is still alive after auto-deployment
  ```bash
  ssh root@<VPS_IP> docker logs notification-bot --tail 5
  ```

## Monitoring & Maintenance

- [ ] Set up process to check bot health periodically
  - Option 1: Manual cron job to send /ping
  - Option 2: Monitor logs for errors
  - Option 3: External monitoring service
- [ ] Know how to restart bot if needed
  ```bash
  docker-compose restart
  ```
- [ ] Know how to rollback to previous version
  ```bash
  git revert <commit-hash>
  git push origin main
  ```
- [ ] Document your VPS path and credentials securely

## Emergency Procedures

### If Bot Stops Responding

```bash
# 1. Check container status
docker ps | grep notification-bot

# 2. Check logs for errors
docker logs notification-bot | tail -50

# 3. Restart container
docker-compose restart

# 4. If still failing, rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### If Doppler Access Fails

```bash
# 1. Re-authenticate
docker exec notification-bot doppler login

# 2. Verify secrets
docker exec notification-bot doppler secrets

# 3. Restart container
docker-compose restart
```

### If Logs Directory Gets Full

```bash
# 1. Check disk usage
df -h

# 2. Archive and clear logs
docker exec notification-bot sh -c 'tar -czf /app/logs/archive-$(date +%Y%m%d).tar.gz /app/logs/log.log && > /app/logs/log.log'

# 3. Download archive if needed
scp root@<VPS_IP>:/path/to/notification-bot/logs/archive-*.tar.gz ./logs_backup/
```

---

## Sign-Off

- [ ] **All items above are completed**
- [ ] **Bot is running reliably**
- [ ] **GitHub Actions deployment works**
- [ ] **Logs are being captured**
- [ ] **Ready for production use**

**Date Deployed**: ________________  
**Deployed By**: ________________  
**VPS Host**: ________________  

