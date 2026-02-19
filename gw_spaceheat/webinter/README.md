# Adding a new house's dashboard to the Backoffice webpage

This guide walks you through the process of adding a new house's dashboard to the GridWorks backoffice webpage. We'll use `oak` as our example house alias throughout this tutorial.

## Step 1: Configure nginx WebSocket Proxy

### 1.1 Connect to the Visualizer Instance

```bash
ssh -A ubuntu@3.221.195.180
```

### 1.2 Edit nginx Configuration

```bash
sudo nano /etc/nginx/sites-enabled/default
```

### 1.3 Find Available Port

Look for existing WebSocket location blocks (e.g., `wsbeech`, `wsfir`, etc.). Each house uses a unique port number between 8080 and 8090. 

**Note:** If you need more ports, update the Amazon security groups to extend the available port range.

For this example, we'll use port **8080**.

### 1.4 Add WebSocket Proxy Configuration

Add the following configuration block to the nginx file:

```nginx
# OAK GridWorks SCADA WebSocket proxy
location /wsoak {
    proxy_pass http://127.0.0.1:8080/wsoak;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WebSocket specific settings
    proxy_read_timeout 86400;
    proxy_send_timeout 86400;
    proxy_connect_timeout 60;

    # Disable buffering for real-time communication
    proxy_buffering off;
    proxy_cache off;
}
```

### 1.5 Reload nginx

```bash
sudo systemctl reload nginx
```

## Step 2: Deploy and Run WebSocket Server

### 2.1 Clone the Repository

In the visualizer EC2 instance's home directory, create a new directory for the house:

```bash
git clone git@github.com:thegridelectric/gridworks-scada.git oak-webinter
cd oak-webinter
```

### 2.2 Configure Environment Variables

Create a `.env` file with the house-specific configuration:

```bash
nano .env
```

Add the following configuration (replace placeholder values with actual data):

```bash
# Target GNode for this house
GWWEBINTER__TARGET_GNODE=hw1.isone.me.versant.keene.oak.scada

# WebSocket server port (must match nginx configuration)
GWWEBINTER__WEB_PORT=8080

# MQTT Broker Configuration
GWWEBINTER__LINK__HOST=<oak-ip-address>
GWWEBINTER__LINK__PORT=1883
GWWEBINTER__LINK__USERNAME='<mqtt-username>'
GWWEBINTER__LINK__PASSWORD='<mqtt-password>'
```

**Configuration Notes:**
- `GWWEBINTER__WEB_PORT` must match the port used in the nginx configuration
- `GWWEBINTER__LINK__HOST` should be the IP address of the house's primary SCADA
- Username and password should be the Rabbit broker credentials

### 2.3 Start the WebSocket Server

Create a new tmux session to run the server in the background:

```bash
tmux new-session -s oak
./start_websocket_server.sh
```

### 2.4. Test the connection by accessing the house dashboard through the backoffice webpage