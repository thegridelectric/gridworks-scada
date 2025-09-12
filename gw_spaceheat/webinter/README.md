# Web Interface for GridWorks SCADA

A simple web interface that provides relay control functionality through a web browser, connecting to the same RabbitMQ MQTT broker as the admin app.

## Architecture

```
Web Browser ↔ WebSocket ↔ Python Server ↔ RabbitMQ MQTT ↔ SCADA System
```

## Features

- Simple HTML page with relay control button
- WebSocket connection for real-time communication
- MQTT bridge to RabbitMQ broker
- Automatic reconnection on connection loss
- Same message protocol as the admin app

## Usage

### Start the web interface server:

```bash
cd /Users/thomas/github/gridworks-scada/gw_spaceheat
python -m webinter.cli serve
```

### Access the web interface:

Open your browser and go to: http://localhost:8080

### Command line options:

```bash
python -m webinter.cli serve --help
```

Options:
- `--target`: Target SCADA system (default: d1.isone.me.versant.keene.orange.scada)
- `--port`: Web server port (default: 8080)
- `--host`: Web server host (default: localhost)
- `--verbose`: Enable verbose logging
- `--paho-verbose`: Enable MQTT client verbose logging

### Configuration:

The web interface uses the same configuration system as the admin app, with the `GWWEBINTER_` prefix:

```bash
export GWWEBINTER_TARGET_GNODE="your.scada.system"
export GWWEBINTER_LINK__HOST="localhost"
export GWWEBINTER_LINK__PORT=1885
export GWWEBINTER_LINK__USERNAME="smqPublic"
export GWWEBINTER_LINK__PASSWORD="smqPublic"
```

## How it works

1. **WebSocket Server**: The Python server creates a WebSocket endpoint that browsers can connect to
2. **MQTT Bridge**: The server connects to the same RabbitMQ MQTT broker as the admin app
3. **Message Translation**: WebSocket messages are translated to MQTT messages and vice versa
4. **Relay Control**: The web page sends relay control commands that are forwarded to the SCADA system

## Message Flow

1. User clicks relay button in browser
2. JavaScript sends WebSocket message to Python server
3. Python server creates MQTT message (same format as admin app)
4. MQTT message is sent to RabbitMQ broker
5. SCADA system receives and processes the command
6. Status updates flow back through the same path

## Dependencies

The web interface requires these additional Python packages:
- `websockets` - WebSocket server
- `aiohttp` - HTTP server for serving the HTML page

Install with:
```bash
pip install websockets aiohttp
```
