#!/bin/bash
# target.sh - Target configuration with deliberate weaknesses for 0.c0011

set -euo pipefail

log_info() { echo "[TARGET] $1"; }

log_info "Configuring deliberate weaknesses..."

# Weak credentials
log_info "Setting up weak credentials..."
useradd -m -s /bin/bash victim 2>/dev/null || true
echo "victim:victim123" | chpasswd 2>/dev/null || true

# Enable password authentication for SSH
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null || true
sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null || true
systemctl restart ssh || true

# Create vulnerable web directory
log_info "Setting up vulnerable web resources..."
mkdir -p /var/www/html
chmod 777 /var/www/html 2>/dev/null || true

# Create decoy sensitive files
log_info "Creating decoy sensitive files..."
mkdir -p /home/victim/Documents
echo "password: secret123" > /home/victim/Documents/credentials.txt
echo "AWS_KEY=AKIAIOSFODNN7EXAMPLE" > /home/victim/.env
echo "api_key: sk-test-123456789" > /home/victim/apikey.txt

# Create writable system directories for persistence testing
mkdir -p /tmp/.hidden
chmod 777 /tmp/.hidden

# Set up cron for testing
(crontab -l 2>/dev/null; echo "* * * * * /bin/true") | crontab - 2>/dev/null || true

# Create SUID binary simulation
chmod u+s /bin/bash 2>/dev/null || true

log_info "Target configuration complete"
log_info "Weaknesses configured: weak creds, SSH password auth, writable dirs"
