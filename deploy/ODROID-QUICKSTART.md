# ODROID C4 Quick Start Guide

## Prerequisites
- ODROID C4 with Armbian installed and SSH access
- NFS server with your music library configured
- k3d cluster on your main machine (optional, for web UI access)

## Step 1: Prepare ODROID C4

Flash Armbian to your ODROID C4's eMMC:
1. Download [Armbian for ODROID-C4](https://www.armbian.com/odroid-c4/)
2. Use Balena Etcher or similar to write to eMMC
3. Boot and complete initial setup
4. Note your ODROID's IP address

## Step 2: Clone and Run Setup

SSH into your ODROID:
```bash
ssh root@your-odroid-ip
```

Clone the repo and run setup:
```bash
cd /tmp
git clone <your-lp-repo-url>
cd lp
chmod +x deploy/rpi-setup.sh
./deploy/rpi-setup.sh
```

This installs all dependencies and sets up the app structure at `/opt/lp`.

## Step 3: Configure NFS Mount

Set up NFS for your music library:
```bash
chmod +x deploy/setup-nfs.sh
./deploy/setup-nfs.sh your-nas-host /path/to/music
```

Or manually add to `/etc/fstab`:
```bash
your-nas-host:/path/to/music    /mnt/music    nfs    defaults,_netdev,nofail    0    0
```

Mount it:
```bash
sudo mount -a
ls /mnt/music  # Should show your music files
```

## Step 4: Configure lp

Copy config:
```bash
sudo cp deploy/config-odroid.yml /etc/lp/config.yml
```

Edit with your settings (display resolution, music path, etc.):
```bash
sudo nano /etc/lp/config.yml
```

Example config:
```yaml
music_library_path: /mnt/music
display:
  fullscreen: true
  width: 1920      # Your display resolution
  height: 1080
api:
  host: "0.0.0.0"
  port: 8000
lastfm:
  api_key: ""
  api_secret: ""
```

## Step 5: Set Up Systemd Service

```bash
sudo cp deploy/lp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lp
sudo systemctl start lp
```

Verify it's running:
```bash
sudo systemctl status lp
sudo journalctl -u lp -f  # Watch logs
```

Access the web UI at: `http://your-odroid-ip:8000`

## Step 6 (Optional): Expose via k3d

Edit `deploy/k3d-ingress.yaml` on your main machine:
- Replace `ODROID_IP` with your ODROID's IP (e.g., `192.168.1.100`)
- Replace `music.example.com` with your domain

Apply it:
```bash
kubectl apply -f deploy/k3d-ingress.yaml
```

Then access via: `https://music.example.com`

## Troubleshooting

### Service won't start
```bash
sudo journalctl -u lp -n 50
```

Common issues:
- **NFS not mounted**: `mount | grep /mnt/music` or run `sudo mount -a`
- **Config permissions**: `sudo chown root:root /etc/lp/config.yml`
- **Display issues**: Check `DISPLAY=:0` in the service file

### No video output
- Try different DISPLAY values (`:0`, `:1`, etc.)
- Ensure X server is running: `ps aux | grep X`
- Check graphics driver: `lsmod | grep mali` or `dmesg | grep gpu`

### NFS issues
```bash
# Check if NFS is reachable
showmount -e your-nas-host

# Remount
sudo umount /mnt/music
sudo mount -a
```

## Maintenance

Update lp:
```bash
cd /opt/lp
sudo git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lp
```

View logs:
```bash
sudo journalctl -u lp -f
```

Restart service:
```bash
sudo systemctl restart lp
```
