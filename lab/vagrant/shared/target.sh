#!/bin/bash
# target.sh - Target configuration with deliberate weaknesses for 0.c0011

set -euo pipefail

log_info() { echo "[TARGET] $1"; }

log_info "Configuring deliberate weaknesses..."

# Weak credentials
log_info "Setting up weak credentials..."
if ! id -u victim >/dev/null 2>&1; then
    useradd -m -s /bin/bash victim
fi
echo "victim:victim123" | chpasswd

# Enable password authentication for SSH
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
systemctl restart ssh

# Create vulnerable web directory
log_info "Setting up vulnerable web resources..."
mkdir -p /var/www/html
chmod 777 /var/www/html

# Create decoy sensitive files
log_info "Creating decoy sensitive files..."
mkdir -p /home/victim/Documents
echo "password: secret123" > /home/victim/Documents/credentials.txt
echo "AWS_KEY=LAB_AWS_KEY_PLACEHOLDER" > /home/victim/.env
echo "api_key: LAB_API_KEY_PLACEHOLDER" > /home/victim/apikey.txt

# Create writable system directories for persistence testing
mkdir -p /tmp/.hidden
chmod 777 /tmp/.hidden

# Set up cron for testing
(crontab -l 2>/dev/null || true; echo "* * * * * /bin/true") | crontab -

# Create SUID binary simulation
chmod u+s /bin/bash

log_info "Target configuration complete"
log_info "Weaknesses configured: weak creds, SSH password auth, writable dirs"
