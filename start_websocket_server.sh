#!/bin/bash

# Simple startup script for the websocket server on EC2
# This script should be run in a tmux session on your EC2 instance

echo "Starting GridWorks SCADA WebSocket Server..."

# Change to the project directory
cd /home/ubuntu/gridworks-scada

# Activate virtual environment if it exists
if [ -d "gw_spaceheat/venv" ]; then
    echo "Activating virtual environment..."
    source gw_spaceheat/venv/bin/activate
fi

# Start the websocket server (it will read .env automatically)
echo "Starting server..."
python -m gw_spaceheat.webinter.cli --host 0.0.0.0 --port 8080 --verbose

echo "Server stopped."