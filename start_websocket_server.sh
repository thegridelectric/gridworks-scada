# Startup script for the websocket server, run in a tmux session on EC2

echo "Starting GridWorks SCADA WebSocket Server..."

cd /home/ubuntu/gridworks-scada

if [ -d "gw_spaceheat/venv" ]; then
    echo "Activating virtual environment..."
    source gw_spaceheat/venv/bin/activate
fi

echo "Starting server..."
python -m gw_spaceheat.webinter.cli --host 0.0.0.0 --port 8080 --verbose

echo "Server stopped."