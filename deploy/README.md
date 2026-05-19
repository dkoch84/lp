# lp Deployment Files

This directory contains scripts and configurations for deploying lp to an ODROID C4 with k3d reverse proxy.

## Files

- **rpi-setup.sh** - Initial setup script for Raspberry Pi OS
- **lp.service** - Systemd service unit file for background operation
- **setup-nfs.sh** - Helper script to configure NFS mount
- **config-rpi.yml** - Example configuration for RPi deployment
- **k3d-ingress.yaml** - Kubernetes manifests for reverse proxy
- **DEPLOYMENT.md** - Complete deployment guide

## Quick Start

### On ODROID C4:

```bash
# 1. Clone repo (adjust URL)
cd /tmp
git clone https://github.com/yourusername/lp.git
cd lp

# 2. Run setup
./deploy/rpi-setup.sh

# 3. Configure NFS
./deploy/setup-nfs.sh nas.local /export/music

# 4. Set up config
sudo cp deploy/config-rpi.yml /etc/lp/config.yml
sudo nano /etc/lp/config.yml  # Adjust as needed

# 5. Start service
sudo cp deploy/lp.service /etc/systemd/system/
sudo systemctl enable lp && sudo systemctl start lp

# 6. Check status
sudo systemctl status lp
```

### On k3d Host:

```bash
# 1. Edit the ingress manifest with your ODROID C4 IP and domain
nano deploy/k3d-ingress.yaml
# Replace:
#   - ODROID_IP with your ODROID C4's IP (e.g., 192.168.1.100)
#   - music.example.com with your domain

# 2. Apply it
kubectl apply -f deploy/k3d-ingress.yaml

# 3. Verify
kubectl get pods
kubectl logs -f deployment/lp-proxy
```

See **DEPLOYMENT.md** for detailed instructions and troubleshooting.
