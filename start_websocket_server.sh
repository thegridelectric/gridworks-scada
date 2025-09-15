#!/bin/bash

# Simple startup script for the websocket server on EC2
# This script should be run in a tmux session on your EC2 instance

echo "Starting GridWorks SCADA WebSocket Server..."

# Change to the project directory
cd /path/to/your/gridworks-scada

# Activate virtual environment if it exists
if [ -d "gw_spaceheat/venv" ]; then
    echo "Activating virtual environment..."
    source gw_spaceheat/venv/bin/activate
fi

# Set environment variables for EC2 deployment
export GWWEBINTER__WEB_HOST=0.0.0.0  # Listen on all interfaces
export GWWEBINTER__WEB_PORT=8080     # Port for the websocket server
export GWWEBINTER__TARGET_GNODE=d1.isone.me.versant.keene.orange.scada  # Your target gnode

# Start the websocket server
echo "Starting server on 0.0.0.0:8080..."
python -m gw_spaceheat.webinter.cli serve --host 0.0.0.0 --port 8080 --verbose

echo "Server stopped."
