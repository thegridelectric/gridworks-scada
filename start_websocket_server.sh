# Startup script for the websocket server, run in a tmux session on EC2

echo "Starting GridWorks SCADA WebSocket Server..."

if [ -d "/home/ubuntu/gridworks-scada/gw_spaceheat/venv" ]; then
    echo "Activating virtual environment..."
    source /home/ubuntu/gridworks-scada/gw_spaceheat/venv/bin/activate
fi

echo "Starting server..."
python -m gw_spaceheat.webinter.cli --verbose

echo "Server stopped."