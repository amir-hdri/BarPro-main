#!/bin/bash
# BarPro Multi-Server Deployment Script
# This script automates the deployment of BarPro to Node 1 (Main App) and Node 2 (Proxy).

# Exit on error
set -e

# Default configurations
NODE1_IP="188.121.123.16"
NODE2_IP="95.38.233.90"
DEFAULT_USER="ubuntu"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================="
echo "        🚀 BarPro Multi-Server Deployment Automation 🚀"
echo "================================================================="
echo "Node 1 (Main Application): $NODE1_IP"
echo "Node 2 (Egress Squid Proxy): $NODE2_IP"
echo "================================================================="
echo ""

# Ask what to deploy
echo "What would you like to deploy?"
echo "1) Deploy Squid Proxy to Node 2 only (95.38.233.90)"
echo "2) Deploy Main Application to Node 1 only (188.121.123.16)"
echo "3) Deploy Both (Full Stack)"
read -rp "Enter choice [1-3]: " DEPLOY_CHOICE

# Prompt for SSH username
read -rp "Enter SSH username for servers [default: $DEFAULT_USER]: " SSH_USER
SSH_USER="${SSH_USER:-$DEFAULT_USER}"

# Helper function to install docker on remote machine
install_docker_remote() {
    local host=$1
    local user=$2
    echo "🔍 Checking Docker installation on $host..."
    ssh -o StrictHostKeyChecking=no "${user}@${host}" "
        if ! command -v docker &> /dev/null; then
            echo 'Installing Docker...'
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose
            sudo systemctl enable docker
            sudo systemctl start docker
            sudo usermod -aG docker \$USER
            echo 'Docker installed successfully!'
        else
            echo 'Docker is already installed.'
        fi
    "
}

# --- DEPLOY NODE 2 (PROXY) ---
deploy_node2() {
    echo ""
    echo "================================================================="
    echo "➡️  Deploying Egress Proxy to Node 2 ($NODE2_IP)"
    echo "================================================================="
    
    install_docker_remote "$NODE2_IP" "$SSH_USER"
    
    echo "📝 Generating Squid configuration for Node 2..."
    TMP_DIR=$(mktemp -d)
    
    cat <<EOF > "${TMP_DIR}/squid.conf"
# Squid Proxy Configuration on Node 2
http_port 3128

# Access Control List (ACL)
# ONLY allow Node 1 to connect to this proxy
acl server1 src $NODE1_IP

http_access allow server1
http_access allow localhost
http_access deny all

# Bind outgoing traffic to the public IP of Node 2
tcp_outgoing_address $NODE2_IP

# Disable caching
cache deny all
EOF

    cat <<EOF > "${TMP_DIR}/docker-compose.yml"
version: '3.8'

services:
  squid:
    image: ubuntu/squid:latest
    container_name: remote_squid
    restart: unless-stopped
    volumes:
      - ./squid.conf:/etc/squid/squid.conf:ro
    ports:
      - "3128:3128"
EOF

    echo "📤 Transferring Squid files to Node 2..."
    ssh -o StrictHostKeyChecking=no "${SSH_USER}@${NODE2_IP}" "sudo mkdir -p /opt/squid && sudo chown -R \$USER:\$USER /opt/squid"
    scp -o StrictHostKeyChecking=no "${TMP_DIR}/squid.conf" "${TMP_DIR}/docker-compose.yml" "${SSH_USER}@${NODE2_IP}:/opt/squid/"
    
    echo "⚙️ Starting Squid Proxy container on Node 2..."
    ssh -o StrictHostKeyChecking=no "${SSH_USER}@${NODE2_IP}" "cd /opt/squid && docker compose up -d"
    
    echo "🧹 Cleaning up temp local files..."
    rm -rf "$TMP_DIR"
    
    echo "✅ Node 2 Proxy deployed successfully!"
}

# --- DEPLOY NODE 1 (MAIN APP) ---
deploy_node1() {
    echo ""
    echo "================================================================="
    echo "➡️  Deploying Main Application to Node 1 ($NODE1_IP)"
    echo "================================================================="
    
    install_docker_remote "$NODE1_IP" "$SSH_USER"
    
    echo "📦 Archiving codebase..."
    TMP_TAR=$(mktemp /tmp/barpro_deploy_XXXXXX.tar.gz)
    
    # Pack files, excluding unnecessary files to keep size small
    tar --exclude='.git' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='output/*' \
        --exclude='*.log' \
        --exclude='__pycache__' \
        --exclude='.mypy_cache' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='*.pyc' \
        -czf "$TMP_TAR" .
        
    echo "📝 Preparing production .env file..."
    TMP_ENV=$(mktemp /tmp/barpro_env_XXXXXX)
    
    if [ -f .env ]; then
        # Copy base variables but overwrite URLs and Proxy configurations
        grep -v -E "^(FRONTEND_URL|NEXT_PUBLIC_API_URL|AVAILABLE_IP_INDICES|WORKER_1_PROXY|WORKER_2_PROXY|WORKER_3_PROXY|ENVIRONMENT)" .env > "$TMP_ENV" || true
    fi
    
    # Append production overrides
    cat <<EOF >> "$TMP_ENV"
ENVIRONMENT="production"
FRONTEND_URL="http://$NODE1_IP"
FRONTEND_URLS="http://${NODE2_IP}"
NEXT_PUBLIC_API_URL="/api"
AVAILABLE_IP_INDICES="1,2"
WORKER_1_PROXY="http://squid_1:3128"
WORKER_2_PROXY="http://${NODE2_IP}:3128"
EOF

    echo "📤 Transferring files to Node 1..."
    ssh -o StrictHostKeyChecking=no "${SSH_USER}@${NODE1_IP}" "sudo mkdir -p /opt/barpro && sudo chown -R \$USER:\$USER /opt/barpro"
    scp -o StrictHostKeyChecking=no "$TMP_TAR" "${SSH_USER}@${NODE1_IP}:/opt/barpro/code.tar.gz"
    scp -o StrictHostKeyChecking=no "$TMP_ENV" "${SSH_USER}@${NODE1_IP}:/opt/barpro/.env"
    
    echo "⚙️ Extracting codebase and starting Docker containers on Node 1..."
    ssh -o StrictHostKeyChecking=no "${SSH_USER}@${NODE1_IP}" "
        cd /opt/barpro
        tar -xzf code.tar.gz
        rm code.tar.gz
        
        # Configure squid_1 egress IP locally
        sed -i 's/IP_ADDRESS_1/$NODE1_IP/g' infra/squid/squid_1.conf
        
        # Start containers (excluding Worker 3 / Squid 3 / Squid 2)
        docker compose --profile docker-backend up -d --build postgres redis squid_1 backend celery_worker_1 celery_worker_2 celery_beat frontend nginx prometheus
        
        # Configure local backup executable
        chmod +x scripts/db_backup.sh
        
        # Configure cronjob for daily backup at 3:00 AM
        (crontab -l 2>/dev/null | grep -F -v '/opt/barpro/scripts/db_backup.sh'; echo '0 3 * * * /opt/barpro/scripts/db_backup.sh >> /opt/barpro/output/backups.log 2>&1') | crontab -
    "
    
    echo "🧹 Cleaning up temp local files..."
    rm -f "$TMP_TAR" "$TMP_ENV"
    
    echo "✅ Node 1 Main Application deployed successfully!"
}

# Execute choices
case $DEPLOY_CHOICE in
    1)
        deploy_node2
        ;;
    2)
        deploy_node1
        ;;
    3)
        deploy_node2
        deploy_node1
        ;;
    *)
        echo "❌ Invalid choice."
        exit 1
        ;;
esac

echo ""
echo "================================================================="
echo "🎉 Deployment Completed Successfully! 🎉"
echo "================================================================="
echo "You can access the BarPro Frontend at: http://$NODE1_IP"
echo "================================================================="
