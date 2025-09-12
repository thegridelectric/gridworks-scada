# GridWorks SCADA Web Interface - Deployment Guide

This guide will help you deploy the GridWorks SCADA web interface to work with your EC2 instance and GitHub Pages.

## Architecture

```
GitHub Pages (HTML) ↔ WebSocket → EC2 (nginx proxy) → Python WebSocket Server → MQTT → SCADA System
```

## Prerequisites

- EC2 instance with nginx already running
- GitHub repository for your website
- Access to your SCADA system's MQTT broker

## Step 1: Deploy WebSocket Server to EC2

### 1.1 Upload Project Files

Upload the entire `gridworks-scada` project to your EC2 instance:

```bash
# From your local machine
scp -r /Users/thomas/github/gridworks-scada ubuntu@your-ec2-domain.com:/home/ubuntu/
```

### 1.2 Run Deployment Script

SSH into your EC2 instance and run the deployment script:

```bash
ssh ubuntu@your-ec2-domain.com
cd /home/ubuntu/gridworks-scada/gw_spaceheat/webinter
chmod +x deploy.sh
./deploy.sh
```

The deployment script will:
- Set up the Python virtual environment
- Install dependencies
- Create a systemd service
- Configure nginx to proxy WebSocket connections
- Start the web interface service

### 1.3 Verify Deployment

Check that the service is running:

```bash
sudo systemctl status gwspaceheat-webinter
sudo journalctl -u gwspaceheat-webinter -f
```

## Step 2: Configure GitHub Pages

### 2.1 Update HTML Configuration

Edit the `index_production.html` file and update the WebSocket configuration:

```javascript
const WEBSOCKET_CONFIG = {
    host: 'your-ec2-domain.com',  // Replace with your actual EC2 domain or IP
    port: 443,  // Use 443 for HTTPS/WSS, or 80 for HTTP/WS
    useSSL: true  // Set to true if using HTTPS/WSS
};
```

### 2.2 Add to GitHub Pages

1. Copy the `index_production.html` file to your GitHub Pages repository
2. Rename it to `scada.html` (or whatever you prefer)
3. Commit and push to trigger GitHub Pages deployment

### 2.3 Test the Integration

Visit your GitHub Pages site at `https://your-username.github.io/your-repo/scada.html`

## Step 3: Configure nginx (if needed)

If the deployment script didn't automatically configure nginx, you can manually add this to your nginx configuration:

```nginx
# Add to your nginx site configuration
location /ws {
    proxy_pass http://127.0.0.1:8080;
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

Then reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Troubleshooting

### WebSocket Connection Issues

1. **Check service status:**
   ```bash
   sudo systemctl status gwspaceheat-webinter
   ```

2. **View service logs:**
   ```bash
   sudo journalctl -u gwspaceheat-webinter -f
   ```

3. **Test WebSocket endpoint:**
   ```bash
   curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Key: test" -H "Sec-WebSocket-Version: 13" http://localhost:8080/ws
   ```

4. **Check nginx configuration:**
   ```bash
   sudo nginx -t
   ```

### MQTT Connection Issues

1. **Verify MQTT broker settings** in the service file:
   ```bash
   sudo systemctl edit gwspaceheat-webinter
   ```

2. **Check if MQTT broker is accessible:**
   ```bash
   telnet localhost 1885
   ```

### Firewall Issues

Make sure your EC2 security group allows:
- Port 80 (HTTP)
- Port 443 (HTTPS)
- Port 8080 (internal WebSocket server)

## Configuration Options

### Environment Variables

You can customize the deployment by setting these environment variables in the systemd service:

```bash
sudo systemctl edit gwspaceheat-webinter
```

Add:
```ini
[Service]
Environment=GWWEBINTER_TARGET_GNODE=your.scada.system
Environment=GWWEBINTER_LINK__HOST=your-mqtt-broker-host
Environment=GWWEBINTER_LINK__PORT=1885
Environment=GWWEBINTER_LINK__USERNAME=your-username
Environment=GWWEBINTER_LINK__PASSWORD=your-password
```

### Service Management

```bash
# Start service
sudo systemctl start gwspaceheat-webinter

# Stop service
sudo systemctl stop gwspaceheat-webinter

# Restart service
sudo systemctl restart gwspaceheat-webinter

# Enable auto-start on boot
sudo systemctl enable gwspaceheat-webinter

# Disable auto-start
sudo systemctl disable gwspaceheat-webinter
```

## Security Considerations

1. **HTTPS/WSS**: Use HTTPS for your GitHub Pages site and WSS for WebSocket connections
2. **Firewall**: Only expose necessary ports
3. **MQTT Security**: Use proper authentication for your MQTT broker
4. **Access Control**: Consider adding authentication to the web interface if needed

## Monitoring

Monitor your deployment:

```bash
# Service status
sudo systemctl status gwspaceheat-webinter

# Real-time logs
sudo journalctl -u gwspaceheat-webinter -f

# System resources
htop
df -h
```

## Support

If you encounter issues:

1. Check the service logs first
2. Verify nginx configuration
3. Test WebSocket connectivity
4. Check MQTT broker connectivity
5. Review firewall settings
