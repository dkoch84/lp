# lp Deployment Guide

## ODROID C4 Setup

### 1. Initial System Setup

Flash Armbian to eMMC using [Armbian for ODROID-C4](https://www.armbian.com/odroid-c4/):
- Download latest Armbian stable release
- Use Balena Etcher or similar to flash to eMMC
- Enable SSH during first boot (follow Armbian prompts)
- Configure network and hostname

SSH into your ODROID:
```bash
ssh root@odroid-c4.local
# or
ssh root@192.168.1.XXX
```

### 2. Run Setup Script

```bash
curl -O https://raw.githubusercontent.com/yourusername/lp/master/deploy/rpi-setup.sh
chmod +x rpi-setup.sh
./rpi-setup.sh
```

This installs all dependencies and creates the app structure.

### 3. Configure NFS Mount

Edit `/etc/fstab` to add your NFS share:
```bash
sudo nano /etc/fstab
```

Add a line like:
```
nas.local:/export/music    /mnt/music    nfs    defaults,_netdev,nofail    0    0
```

Or run the helper script:
```bash
deploy/setup-nfs.sh nas.local /export/music
```

Test the mount:
```bash
sudo mount -a
ls /mnt/music
```

### 4. Configure the Application

Copy example config and edit:
```bash
sudo cp config.example.yml /etc/lp/config.yml
sudo nano /etc/lp/config.yml
```

Set the music library path to your NFS mount:
```yaml
music_library_path: /mnt/music
display:
  fullscreen: true
  width: 1920
  height: 1080
lastfm:
  api_key: ""
  api_secret: ""
```

Adjust display resolution to your connected display.

### 5. Set Up Systemd Service

```bash
sudo cp deploy/lp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lp
sudo systemctl start lp
```

Check the service:
```bash
sudo systemctl status lp
sudo journalctl -u lp -f
```

The web UI should be available at `http://odroid-c4.local:8000` (or your ODROID's IP).

---

## k3d Reverse Proxy Setup

### 1. Prepare the Ingress Manifest

Edit `deploy/k3d-ingress.yaml`:
- Replace `RPI_IP` with your RPi's IP address (e.g., `192.168.1.100`)
- Replace `music.example.com` with your actual domain
- Ensure the TLS secret name matches your existing setup

### 2. Apply to k3d

```bash
kubectl apply -f deploy/k3d-ingress.yaml
```

### 3. Verify the Proxy

Check that the proxy deployment is running:
```bash
kubectl get deployments
kubectl get pods
kubectl logs -f deployment/lp-proxy
```

Check the Ingress:
```bash
kubectl get ingress
```

### 4. Access Through Your Cluster

Your lp web UI should now be accessible at:
```
https://music.example.com
```

Through your k3d cluster's existing TLS termination and DNS setup.

---

## Troubleshooting

### ODROID: Service won't start
```bash
sudo journalctl -u lp -n 50
```

Common issues:
- Config file permissions: `sudo chown root:root /etc/lp/config.yml`
- NFS not mounted: `mount | grep /mnt/music`
- Display not found: Check if DISPLAY variable is set correctly (may need `:0` or `:1`)
- Graphics permissions: Ensure the X server is running and accessible to root

### k3d: Proxy shows 502 Bad Gateway
- Verify ODROID IP is correct in ConfigMap
- Check ODROID API is running: `curl http://odroid-c4.local:8000`
- Check network connectivity from k3d node to ODROID

### NFS mount issues
```bash
# Force remount
sudo umount /mnt/music
sudo mount -a

# Check NFS connectivity
showmount -e nas.local
```

---

## Maintenance

### Update lp on ODROID

```bash
cd /opt/lp
sudo git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lp
```

### View Logs

```bash
# Systemd journal
sudo journalctl -u lp -f

# Last 50 lines
sudo journalctl -u lp -n 50
```

### Restart Service

```bash
sudo systemctl restart lp
```
