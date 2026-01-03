#!/bin/bash
# Start Morning Drive in development mode with auto-reload

# Detect host IP for the admin panel
export SERVER_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')

echo "Starting Morning Drive in development mode..."
echo "Server IP: $SERVER_IP"
echo "Admin panel: http://localhost:8000/admin"
echo "API docs: http://localhost:8000/api/docs"
echo ""
echo "Source code is mounted - changes will auto-reload!"

docker compose up -d

echo ""
echo "Logs: docker compose logs -f morning-drive"
