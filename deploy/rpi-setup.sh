#!/bin/bash
# ODROID C4 setup script for lp music player
# Run this on a fresh Armbian/Ubuntu installation on ODROID C4

set -e

echo "📀 Setting up lp music player on ODROID C4..."

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    vlc libvlc-dev \
    libsdl2-dev libsdl2-image-dev \
    git \
    nfs-common

# Create app directory
APP_DIR="/opt/lp"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Clone repository (adjust URL as needed)
echo "Cloning lp repository..."
cd $APP_DIR
if [ ! -d .git ]; then
    git clone https://github.com/yourusername/lp.git .
else
    git pull
fi

# Set up Python virtual environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create config directory
mkdir -p /etc/lp
sudo chown $USER:$USER /etc/lp

# Create NFS mount point
echo "Setting up NFS mount point..."
mkdir -p /mnt/music
# User should edit /etc/fstab to add NFS mount like:
# nas.local:/export/music  /mnt/music  nfs  defaults,_netdev  0  0

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure NFS mount in /etc/fstab if not already done"
echo "2. Create config file: sudo cp config.example.yml /etc/lp/config.yml"
echo "3. Edit /etc/lp/config.yml with your music path (e.g., /mnt/music)"
echo "4. Run: sudo cp deploy/lp.service /etc/systemd/system/"
echo "5. Update service file: sudo chown root:root /etc/systemd/system/lp.service"
echo "6. Enable service: sudo systemctl daemon-reload && sudo systemctl enable lp && sudo systemctl start lp"
echo "7. Check status: sudo systemctl status lp"
