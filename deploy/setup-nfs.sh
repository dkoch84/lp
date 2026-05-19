#!/bin/bash
# Setup NFS mount for lp music library on Raspberry Pi

set -e

NFS_SERVER="${1:-nas.local}"
NFS_EXPORT="${2:-/export/music}"
MOUNT_POINT="/mnt/music"

echo "📀 Setting up NFS mount for lp music library"
echo "  Server: $NFS_SERVER"
echo "  Export: $NFS_EXPORT"
echo "  Mount point: $MOUNT_POINT"

# Create mount point
sudo mkdir -p $MOUNT_POINT

# Add to /etc/fstab if not already present
if ! grep -q "$NFS_SERVER:$NFS_EXPORT" /etc/fstab; then
    echo "Adding NFS mount to /etc/fstab..."
    echo "$NFS_SERVER:$NFS_EXPORT  $MOUNT_POINT  nfs  defaults,_netdev,nofail  0  0" | sudo tee -a /etc/fstab
else
    echo "NFS mount already in /etc/fstab"
fi

# Mount it
echo "Mounting NFS share..."
sudo mount -a

# Verify
if mountpoint -q $MOUNT_POINT; then
    echo "✅ NFS mount successful!"
    ls -la $MOUNT_POINT
else
    echo "❌ NFS mount failed. Check your NFS server and network."
    exit 1
fi
