#!/bin/bash
# Build and push Morning Drive backend to Docker Hub
#
# Usage:
#   ./scripts/build-and-push.sh                    # Uses 'latest' tag
#   ./scripts/build-and-push.sh v1.0.0             # Uses specified tag
#   ./scripts/build-and-push.sh v1.0.0 myusername  # Uses specified tag and username
#
# Environment variables:
#   DOCKER_USERNAME - Docker Hub username (required if not passed as argument)

set -e

# Configuration
IMAGE_NAME="morning-drive"
TAG="${1:-latest}"
DOCKER_USERNAME="${2:-${DOCKER_USERNAME}}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and change to backend root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Morning Drive - Build & Push Script  ${NC}"
echo -e "${GREEN}========================================${NC}"

# Check for Docker Hub username
if [ -z "$DOCKER_USERNAME" ]; then
    echo -e "${YELLOW}Docker Hub username not set.${NC}"
    read -p "Enter your Docker Hub username: " DOCKER_USERNAME
    if [ -z "$DOCKER_USERNAME" ]; then
        echo -e "${RED}Error: Docker Hub username is required${NC}"
        exit 1
    fi
fi

FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}"

echo ""
echo -e "Image: ${GREEN}${FULL_IMAGE_NAME}:${TAG}${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running. Please start Docker and try again.${NC}"
    exit 1
fi

# Check if logged in to Docker Hub
if ! docker info 2>/dev/null | grep -q "Username"; then
    echo -e "${YELLOW}Not logged in to Docker Hub. Please log in:${NC}"
    docker login
fi

# Build the image
echo -e "${GREEN}Building Docker image...${NC}"
docker build --platform linux/amd64 -t "${FULL_IMAGE_NAME}:${TAG}" .

# Also tag as latest if a version tag was provided
if [ "$TAG" != "latest" ]; then
    echo -e "${GREEN}Also tagging as latest...${NC}"
    docker tag "${FULL_IMAGE_NAME}:${TAG}" "${FULL_IMAGE_NAME}:latest"
fi

# Push to Docker Hub
echo -e "${GREEN}Pushing to Docker Hub...${NC}"
docker push "${FULL_IMAGE_NAME}:${TAG}"

if [ "$TAG" != "latest" ]; then
    docker push "${FULL_IMAGE_NAME}:latest"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Successfully pushed!                 ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Image available at: ${GREEN}docker pull ${FULL_IMAGE_NAME}:${TAG}${NC}"
echo ""
echo -e "To deploy, copy ${YELLOW}docker-compose.prod.yml${NC} to your server"
echo -e "and run: ${GREEN}docker compose -f docker-compose.prod.yml up -d${NC}"
