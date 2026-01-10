#!/bin/bash
# SSH Tunnel to Windows Server for Remote Monitoring
#
# Usage: ./tunnel.sh user@windows-server-ip
#
# This script establishes an SSH tunnel that forwards all monitoring
# ports from the Windows server to your local Mac.
#
# Ports forwarded:
#   8000 - FastAPI API (metrics at /metrics)
#   5555 - Flower (Celery monitoring UI)
#   9187 - PostgreSQL exporter
#   9121 - Redis exporter
#   9182 - Windows host exporter (CPU, RAM, disk)

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 user@windows-server-ip"
    echo ""
    echo "Example: $0 admin@192.168.1.100"
    echo ""
    echo "This will forward the following ports:"
    echo "  - 8000: FastAPI API + metrics"
    echo "  - 5555: Flower (Celery UI)"
    echo "  - 9187: PostgreSQL exporter"
    echo "  - 9121: Redis exporter"
    exit 1
fi

TARGET="$1"

echo "=========================================="
echo "  Whisper Monitoring SSH Tunnel"
echo "=========================================="
echo ""
echo "Connecting to: $TARGET"
echo ""
echo "Forwarding ports:"
echo "  localhost:8000 -> Windows:8000 (API + metrics)"
echo "  localhost:5555 -> Windows:5555 (Flower)"
echo "  localhost:9187 -> Windows:9187 (Postgres exporter)"
echo "  localhost:9121 -> Windows:9121 (Redis exporter)"
echo "  localhost:9182 -> Windows:9182 (Windows host metrics)"
echo ""
echo "Press Ctrl+C to disconnect"
echo "=========================================="
echo ""

# Add -v for verbose output if DEBUG=1
VERBOSE=""
if [ "${DEBUG:-0}" = "1" ]; then
    VERBOSE="-v"
fi

ssh -N $VERBOSE \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -L 8000:127.0.0.1:8000 \
    -L 5555:127.0.0.1:5555 \
    -L 9187:127.0.0.1:9187 \
    -L 9121:127.0.0.1:9121 \
    -L 9182:127.0.0.1:9182 \
    "$TARGET"
