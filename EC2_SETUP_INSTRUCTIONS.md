# GridWorks SCADA WebSocket Server - EC2 Setup Instructions

This guide will help you set up the GridWorks SCADA WebSocket server to run on your EC2 instance with nginx as a reverse proxy.

## Prerequisites

- EC2 instance with Ubuntu/Debian (or similar Linux distribution)
- nginx installed on your EC2 instance
- Python 3.8+ installed
- tmux installed (for running the server in the background)

## Step 1: Upload Your Code to EC2

1. **Upload the project to your EC2 instance:**
   ```bash
   # From your local machine, upload the project
   scp -r /path/to/your/gridworks-scada ubuntu@your-ec2-ip:/home/ubuntu/
   ```

2. **SSH into your EC2 instance:**
   ```bash
   ssh ubuntu@your-ec2-ip
   ```

3. **Navigate to the project directory:**
   ```bash
   cd /home/ubuntu/gridworks-scada
   ```

## Step 2: Set Up Python Environment

1. **Install Python dependencies:**
   ```bash
   # Create virtual environment
   python3 -m venv gw_spaceheat/venv
   
   # Activate virtual environment
   source gw_spaceheat/venv/bin/activate
   
   # Install dependencies
   pip install -r gw_spaceheat/requirements/requirements.txt
   ```

2. **Update the startup script:**
   ```bash
   # Edit the startup script to use the correct path
   nano start_websocket_server.sh
   ```
   
   Change the path in the script:
   ```bash
   cd /home/ubuntu/gridworks-scada  # Update this path
   ```

## Step 3: Configure nginx

1. **Copy the nginx configuration:**
   ```bash
   sudo cp nginx_websocket.conf /etc/nginx/sites-available/gridworks-scada
   ```

2. **Edit the configuration:**
   ```bash
   sudo nano /etc/nginx/sites-available/gridworks-scada
   ```
   
   Update the following:
   - Replace `your-ec2-public-ip-or-domain.com` with your actual EC2 public IP or domain
   - Update the `root` path to `/home/ubuntu/gridworks-scada/gw_spaceheat/webinter`

3. **Enable the site:**
   ```bash
   sudo ln -s /etc/nginx/sites-available/gridworks-scada /etc/nginx/sites-enabled/
   ```

4. **Test nginx configuration:**
   ```bash
   sudo nginx -t
   ```

5. **Restart nginx:**
   ```bash
   sudo systemctl restart nginx
   ```

## Step 4: Configure Security Groups

Make sure your EC2 security group allows:
- **Port 80** (HTTP) - for nginx
- **Port 22** (SSH) - for remote access
- **Port 8080** (optional) - if you want direct access to the Python server

## Step 5: Run the Server in tmux

1. **Start a new tmux session:**
   ```bash
   tmux new-session -d -s gridworks-scada
   ```

2. **Attach to the session:**
   ```bash
   tmux attach-session -t gridworks-scada
   ```

3. **Run the startup script:**
   ```bash
   ./start_websocket_server.sh
   ```

4. **Detach from tmux (keep server running):**
   - Press `Ctrl+B`, then `D`

5. **To reattach to the session later:**
   ```bash
   tmux attach-session -t gridworks-scada
   ```

## Step 6: Access the Web Interface

### Option 1: Direct Access (Recommended)
Open your browser and go to:
```
http://your-ec2-public-ip
```

### Option 2: Local HTML File
1. Download the `index_ec2.html` file to your local computer
2. Open it in your browser
3. Enter your EC2 public IP address
4. Click "Connect to EC2"

## Troubleshooting

### Check if the server is running:
```bash
# Check tmux sessions
tmux list-sessions

# Check if the Python server is listening on port 8080
sudo netstat -tlnp | grep 8080

# Check nginx status
sudo systemctl status nginx
```

### View server logs:
```bash
# Attach to tmux session to see logs
tmux attach-session -t gridworks-scada
```

### Check nginx logs:
```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Restart services:
```bash
# Restart nginx
sudo systemctl restart nginx

# Restart the Python server (in tmux)
tmux attach-session -t gridworks-scada
# Press Ctrl+C to stop, then run ./start_websocket_server.sh again
```

## Environment Variables

You can customize the server behavior by setting these environment variables:

```bash
export GWWEBINTER__WEB_HOST=0.0.0.0
export GWWEBINTER__WEB_PORT=8080
export GWWEBINTER__TARGET_GNODE=your-target-gnode
export GWWEBINTER__LINK__HOST=your-mqtt-broker-host
export GWWEBINTER__LINK__PORT=your-mqtt-broker-port
export GWWEBINTER__LINK__USERNAME=your-mqtt-username
export GWWEBINTER__LINK__PASSWORD=your-mqtt-password
```

## Security Considerations

1. **Use HTTPS in production** - Set up SSL certificates for secure connections
2. **Firewall rules** - Only open necessary ports
3. **Authentication** - Consider adding authentication to the web interface
4. **Regular updates** - Keep your EC2 instance and dependencies updated

## Auto-start on Boot (Optional)

To make the server start automatically when the EC2 instance boots:

1. **Create a systemd service file:**
   ```bash
   sudo nano /etc/systemd/system/gridworks-scada.service
   ```

2. **Add the following content:**
   ```ini
   [Unit]
   Description=GridWorks SCADA WebSocket Server
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/gridworks-scada
   ExecStart=/home/ubuntu/gridworks-scada/start_websocket_server.sh
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable gridworks-scada
   sudo systemctl start gridworks-scada
   ```

This setup provides a simple, reliable way to run your GridWorks SCADA WebSocket server on EC2 with nginx handling the web requests and proxying WebSocket connections to your Python server.
