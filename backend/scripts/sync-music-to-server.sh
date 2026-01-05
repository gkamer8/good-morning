#!/bin/bash
# Sync music pieces from local MinIO to production server
#
# Usage:
#   ./scripts/sync-music-to-server.sh           # Syncs to 'altair' (default)
#   ./scripts/sync-music-to-server.sh myserver  # Syncs to custom SSH host
#
# This script:
#   1. Exports music files from local MinIO
#   2. Copies them to the production server
#   3. Imports them into production MinIO
#   4. Copies the database music_pieces table
#
# Note: This does NOT overwrite existing MinIO data - it adds/updates files.
# The production MinIO uses persistent named volumes that survive deployments.

set -e

# Configuration
SSH_HOST="${1:-altair}"
REMOTE_DIR="~/morning-drive"
LOCAL_EXPORT_DIR="/tmp/morning-drive-music-export"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and change to backend root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Morning Drive - Sync Music to Server ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if local MinIO is running
if ! curl -s http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo -e "${RED}Error: Local MinIO is not running${NC}"
    echo -e "Start it with: docker compose up -d minio"
    exit 1
fi
echo -e "${GREEN}Local MinIO is running${NC}"

# Test SSH connection
echo -e "${YELLOW}Testing SSH connection to ${SSH_HOST}...${NC}"
if ! ssh -o ConnectTimeout=5 "$SSH_HOST" "echo 'Connected'" > /dev/null 2>&1; then
    echo -e "${RED}Error: Cannot connect to ${SSH_HOST}${NC}"
    exit 1
fi
echo -e "${GREEN}SSH connection OK${NC}"
echo ""

# Create local export directory
rm -rf "$LOCAL_EXPORT_DIR"
mkdir -p "$LOCAL_EXPORT_DIR"

# Export files from local MinIO
echo -e "${YELLOW}Exporting music files from local MinIO...${NC}"
docker exec morning-drive-minio sh -c "rm -rf /tmp/music-export; mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null; mc cp --recursive local/morning-drive-music/ /tmp/music-export/"

# Copy files out of container
docker cp morning-drive-minio:/tmp/music-export/. "$LOCAL_EXPORT_DIR/"

FILE_COUNT=$(find "$LOCAL_EXPORT_DIR" -type f -name "*.mp3" | wc -l | tr -d ' ')
echo -e "${GREEN}Found ${FILE_COUNT} music files${NC}"

if [ "$FILE_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No music files to sync${NC}"
    exit 0
fi

# Copy files to production server
echo -e "${YELLOW}Copying music files to ${SSH_HOST}...${NC}"
ssh "$SSH_HOST" "rm -rf /tmp/morning-drive-music-import; mkdir -p /tmp/morning-drive-music-import"
scp -r "$LOCAL_EXPORT_DIR/"* "$SSH_HOST:/tmp/morning-drive-music-import/"

# Import into production MinIO
echo -e "${YELLOW}Importing into production MinIO...${NC}"
ssh "$SSH_HOST" "docker cp /tmp/morning-drive-music-import/. morning-drive-minio:/tmp/music-import/"
ssh "$SSH_HOST" "docker exec morning-drive-minio sh -c 'mc alias set local http://localhost:9000 minioadmin minioadmin && mc mb -p local/morning-drive-music && mc cp --recursive /tmp/music-import/ local/morning-drive-music/'"

# Export local database music_pieces table
echo -e "${YELLOW}Exporting database records...${NC}"
source venv/bin/activate 2>/dev/null || true
python3 -c "
import sqlite3
import json

conn = sqlite3.connect('data/morning_drive.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM music_pieces')
columns = [description[0] for description in cursor.description]
rows = cursor.fetchall()
data = [dict(zip(columns, row)) for row in rows]
print(json.dumps(data))
conn.close()
" > /tmp/music_pieces.json

# Copy and import database records on production
echo -e "${YELLOW}Importing database records...${NC}"
scp /tmp/music_pieces.json "$SSH_HOST:/tmp/"
ssh "$SSH_HOST" "docker cp /tmp/music_pieces.json morning-drive:/tmp/"
ssh "$SSH_HOST" "docker exec morning-drive python3 -c \"
import sqlite3
import json

with open('/tmp/music_pieces.json', 'r') as f:
    pieces = json.load(f)

conn = sqlite3.connect('/app/data/morning_drive.db')
cursor = conn.cursor()

for p in pieces:
    cursor.execute('''
        INSERT OR REPLACE INTO music_pieces
        (id, title, composer, description, s3_key, duration_seconds, file_size_bytes,
         day_of_year_start, day_of_year_end, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (p['id'], p['title'], p['composer'], p.get('description'), p['s3_key'],
          p['duration_seconds'], p.get('file_size_bytes'), p['day_of_year_start'],
          p['day_of_year_end'], p['is_active'], p['created_at']))

conn.commit()
print(f'Imported {len(pieces)} music pieces')
conn.close()
\""

# Cleanup
echo -e "${YELLOW}Cleaning up...${NC}"
rm -rf "$LOCAL_EXPORT_DIR"
rm -f /tmp/music_pieces.json
ssh "$SSH_HOST" "rm -rf /tmp/morning-drive-music-import /tmp/music_pieces.json" 2>/dev/null || true
ssh "$SSH_HOST" "docker exec morning-drive-minio rm -rf /tmp/music-import" 2>/dev/null || true
ssh "$SSH_HOST" "docker exec morning-drive rm -f /tmp/music_pieces.json" 2>/dev/null || true
docker exec morning-drive-minio rm -rf /tmp/music-export 2>/dev/null || true

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Music sync complete!                 ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Synced ${FILE_COUNT} music files to ${SSH_HOST}"
