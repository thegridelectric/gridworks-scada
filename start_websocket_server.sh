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

# Verify .env file exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found in $(pwd)"
    echo "Please create a .env file with your MQTT broker configuration"
    exit 1
fi

echo "Using .env file: $(pwd)/.env"

# Load environment variables from .env file
echo "Loading environment variables from .env file..."
set -a  # automatically export all variables
source .env
set +a  # stop automatically exporting

# Verify some key variables are loaded
echo "Loaded environment variables:"
echo "GWWEBINTER__LINK__HOST: $GWWEBINTER__LINK__HOST"
echo "GWWEBINTER__LINK__PORT: $GWWEBINTER__LINK__PORT"
echo "GWWEBINTER__LINK__USERNAME: $GWWEBINTER__LINK__USERNAME"

# Start the websocket server with environment variables explicitly set
echo "Starting server..."
GWWEBINTER__LINK__HOST="$GWWEBINTER__LINK__HOST" \
GWWEBINTER__LINK__PORT="$GWWEBINTER__LINK__PORT" \
GWWEBINTER__LINK__USERNAME="$GWWEBINTER__LINK__USERNAME" \
GWWEBINTER__LINK__PASSWORD="$GWWEBINTER__LINK__PASSWORD" \
GWWEBINTER__TARGET_GNODE="$GWWEBINTER__TARGET_GNODE" \
GWWEBINTER__WEB_HOST="0.0.0.0" \
GWWEBINTER__WEB_PORT="8080" \
python -m gw_spaceheat.webinter.cli serve --host 0.0.0.0 --port 8080 --verbose

echo "Server stopped."