#!/bin/bash

# OVHCloud VPS Setup Script for notification-bot
# Run this script on your VPS to initialize the application
# Usage: bash VPS_SETUP.sh

set -e

echo "🚀 Initializing notification-bot on OVHCloud VPS"
echo ""

# Step 1: Create directories
echo "📁 Creating directories..."
mkdir -p /opt/notification-bot
mkdir -p /opt/notification-bot/data
mkdir -p /opt/notification-bot/logs
chmod 755 /opt/notification-bot

# Step 2: Clone repository
echo "📥 Cloning repository (you need to do this manually)..."
echo "   Run: cd /opt/notification-bot && git init && git remote add origin <your-repo-url>"
echo "   Then: git fetch origin main && git checkout main"
echo ""

# Step 3: Create .env file template
echo "📝 Creating .env template..."
cat > /opt/notification-bot/.env.template << 'EOF'
# Docker Hub credentials
DOCKER_HUB_USERNAME=your_docker_hub_username

# Doppler token for secrets
NOTIFICATION_BOT_DOPPLER_TOKEN=your_doppler_token_here

# Logging
LOG_LEVEL=INFO
EOF

echo "   ✓ Created /opt/notification-bot/.env.template"
echo "   Edit and rename to .env: cp .env.template .env && nano .env"
echo ""

# Step 4: Copy redeploy script
echo "📋 Setting up redeploy script..."
if [ -f "/opt/notification-bot/scripts/redeploy-notification-bot.sh" ]; then
    cp /opt/notification-bot/scripts/redeploy-notification-bot.sh /opt/redeploy-notification-bot.sh
    chmod +x /opt/redeploy-notification-bot.sh
    echo "   ✓ Copied redeploy script to /opt/redeploy-notification-bot.sh"
else
    echo "   ⚠️  scripts/redeploy-notification-bot.sh not found (clone repository first)"
fi
echo ""

# Step 5: Verify Docker installation
echo "🐳 Checking Docker installation..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo "   ✓ Docker: $DOCKER_VERSION"
else
    echo "   ❌ Docker not installed!"
    echo "   Install with: apt-get install -y docker.io"
    exit 1
fi

if command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version)
    echo "   ✓ Docker Compose: $COMPOSE_VERSION"
else
    echo "   ❌ Docker Compose not installed!"
    echo "   Install with: apt-get install -y docker-compose"
    exit 1
fi
echo ""

# Step 6: Summary
echo "✅ VPS Setup Complete!"
echo ""
echo "📋 Next steps:"
echo "   1. cd /opt/notification-bot"
echo "   2. cp .env.template .env"
echo "   3. nano .env  # Edit with your Docker Hub username and Doppler token"
echo "   4. git init && git remote add origin <your-repo-url>"
echo "   5. git fetch origin main && git checkout main"
echo "   6. docker login -u <your-username>  # Test Docker Hub access"
echo "   7. docker compose pull"
echo "   8. docker compose up -d"
echo ""
echo "🔍 Verify deployment:"
echo "   docker compose ps"
echo "   docker logs -f notification-bot"
echo ""
echo "📚 Full guide: see DEPLOY_SETUP.md in repository"
