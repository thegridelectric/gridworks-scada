#!/bin/bash

# GridWorks SCADA Web Interface Deployment Script
# Run this script on your EC2 instance to deploy the web interface

set -e

echo "🚀 Deploying GridWorks SCADA Web Interface..."

# Configuration
EC2_USER="ubuntu"
PROJECT_DIR="/home/$EC2_USER/gridworks-scada"
SERVICE_NAME="gwspaceheat-webinter"
NGINX_CONFIG="/etc/nginx/sites-available/default"

# Check if running as root or with sudo
if [[ $EUID -eq 0 ]]; then
    echo "❌ Please don't run this script as root. Run as $EC2_USER instead."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "websocket_server.py" ]; then
    echo "❌ Please run this script from the webinter directory"
    exit 1
fi

echo "📁 Setting up project directory..."
sudo mkdir -p $PROJECT_DIR
sudo chown $EC2_USER:$EC2_USER $PROJECT_DIR

# Copy the project files (assuming you've uploaded them)
echo "📋 Copying project files..."
cp -r ../* $PROJECT_DIR/
cd $PROJECT_DIR/gw_spaceheat

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment and install dependencies
echo "📦 Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements/prod.txt 2>/dev/null || pip install aiohttp websockets

# Install the systemd service
echo "⚙️ Installing systemd service..."
sudo cp webinter/$SERVICE_NAME.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

# Configure nginx
echo "🌐 Configuring nginx..."
if [ -f "$NGINX_CONFIG" ]; then
    # Backup existing config
    sudo cp $NGINX_CONFIG $NGINX_CONFIG.backup.$(date +%Y%m%d_%H%M%S)
    
    # Add our WebSocket proxy configuration
    if ! grep -q "location /ws" $NGINX_CONFIG; then
        echo "Adding WebSocket proxy configuration to nginx..."
        sudo tee -a $NGINX_CONFIG > /dev/null << 'EOF'

# GridWorks SCADA Web Interface WebSocket proxy
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
EOF
    else
        echo "WebSocket proxy configuration already exists in nginx config"
    fi
    
    # Test nginx configuration
    echo "Testing nginx configuration..."
    sudo nginx -t
    
    # Reload nginx
    echo "Reloading nginx..."
    sudo systemctl reload nginx
else
    echo "⚠️ Warning: nginx config file not found at $NGINX_CONFIG"
    echo "Please manually add the WebSocket proxy configuration to your nginx setup"
fi

# Start the service
echo "🔄 Starting the web interface service..."
sudo systemctl start $SERVICE_NAME

# Check service status
echo "📊 Service status:"
sudo systemctl status $SERVICE_NAME --no-pager

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update the WEBSOCKET_CONFIG in your HTML file with your EC2 domain/IP"
echo "2. Add the HTML file to your GitHub Pages repository"
echo "3. Test the connection from your GitHub Pages site"
echo ""
echo "🔧 Useful commands:"
echo "  View logs: sudo journalctl -u $SERVICE_NAME -f"
echo "  Restart service: sudo systemctl restart $SERVICE_NAME"
echo "  Check status: sudo systemctl status $SERVICE_NAME"
echo ""
echo "🌐 Your WebSocket server should now be running on ws://your-domain.com/ws"
