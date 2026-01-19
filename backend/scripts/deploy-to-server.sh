#!/bin/bash
# Deploy Morning Drive to a remote server
#
# Usage:
#   ./scripts/deploy-to-server.sh           # Deploys to 'altair' (default)
#   ./scripts/deploy-to-server.sh myserver  # Deploys to custom SSH host
#
# Prerequisites:
#   - SSH config set up for the target host (e.g., ~/.ssh/config)
#   - Docker and Docker Compose installed on the target server

set -e

# Configuration
SSH_HOST="${1:-altair}"
REMOTE_DIR="~/morning-drive"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and change to backend root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Morning Drive - Deploy to Server     ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Target: ${GREEN}${SSH_HOST}:${REMOTE_DIR}${NC}"
echo ""

# Check that required files exist
if [ ! -f "docker-compose.prod.yml" ]; then
    echo -e "${RED}Error: docker-compose.prod.yml not found${NC}"
    exit 1
fi

if [ ! -f ".env.prod.example" ]; then
    echo -e "${RED}Error: .env.prod.example not found${NC}"
    exit 1
fi

# Test SSH connection
echo -e "${YELLOW}Testing SSH connection...${NC}"
if ! ssh -o ConnectTimeout=5 "$SSH_HOST" "echo 'Connected'" > /dev/null 2>&1; then
    echo -e "${RED}Error: Cannot connect to ${SSH_HOST}${NC}"
    echo -e "Make sure your SSH config is set up correctly in ~/.ssh/config"
    exit 1
fi
echo -e "${GREEN}SSH connection OK${NC}"
echo ""

# Create remote directory
echo -e "${YELLOW}Creating remote directory...${NC}"
ssh "$SSH_HOST" "mkdir -p ${REMOTE_DIR}"

# Copy files
echo -e "${YELLOW}Copying deployment files...${NC}"
scp docker-compose.prod.yml "$SSH_HOST:${REMOTE_DIR}/"
scp .env.prod.example "$SSH_HOST:${REMOTE_DIR}/"

# Check if .env already exists on remote
if ssh "$SSH_HOST" "[ -f ${REMOTE_DIR}/.env ]"; then
    echo -e "${YELLOW}Note: .env file already exists on server (not overwritten)${NC}"
else
    echo -e "${YELLOW}Creating .env from template...${NC}"
    ssh "$SSH_HOST" "cp ${REMOTE_DIR}/.env.prod.example ${REMOTE_DIR}/.env"
fi

# Copy assets directory if it exists
if [ -d "assets" ]; then
    echo -e "${YELLOW}Copying audio assets...${NC}"
    scp -r assets "$SSH_HOST:${REMOTE_DIR}/"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment files copied!             ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. SSH to server: ${GREEN}ssh ${SSH_HOST}${NC}"
echo -e "  2. Edit .env file: ${GREEN}cd ${REMOTE_DIR} && nano .env${NC}"
echo -e "     - Add your API keys (ANTHROPIC_API_KEY)"
echo -e "     - Set ADMIN_PASSWORD"
echo -e "  3. Start services: ${GREEN}docker compose -f docker-compose.prod.yml up -d${NC}"
echo ""
