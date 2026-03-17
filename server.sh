#!/usr/bin/env bash
# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
# Start the Mnemos MCP server and dashboard
# Usage: ./server.sh [--dashboard-only | --mcp-only]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

case "${1:-all}" in
    --dashboard-only)
        echo "Starting Mnemos Dashboard on http://localhost:8420"
        python -m mnemos.dashboard.app
        ;;
    --mcp-only)
        echo "Starting Mnemos MCP Server..."
        mnemos
        ;;
    all)
        echo "Starting Mnemos Dashboard on http://localhost:8420"
        python -m mnemos.dashboard.app &
        DASHBOARD_PID=$!
        echo "Dashboard PID: $DASHBOARD_PID"

        echo "Starting Mnemos MCP Server..."
        mnemos &
        MCP_PID=$!
        echo "MCP Server PID: $MCP_PID"

        trap "kill $DASHBOARD_PID $MCP_PID 2>/dev/null; exit" INT TERM
        echo ""
        echo "Both servers running. Press Ctrl+C to stop."
        wait
        ;;
    *)
        echo "Usage: $0 [--dashboard-only | --mcp-only]"
        exit 1
        ;;
esac
