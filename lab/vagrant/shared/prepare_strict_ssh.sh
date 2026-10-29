#!/usr/bin/env bash
set -euo pipefail

# This well-known public key is only the local Vagrant transport identity.
# It is not a campaign credential and no private key is included in a role image.
readonly VAGRANT_PUBLIC_KEY='ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6NF8iallvQVp22WDkTkyrtvp9eWW6A8YVr+kz4TjGYe7gHzIw+niNltGEFHzD8+v1I2YJ6oXevct1YeS0o9HZyN1Q9qgCgzUFtdOKLv6IedplqoPkcmF0aYet2PkEDo3MlTBckFXPITAMzF8dJSIFo9D8HfdOV0IAdx4O7PtixWKn5y2hMNG0zQPyUecp4pzC6kivAIhyfHilFR61RGL+GPXQ2MWZWFYbAGjyiYJnAmCP3NOTd0jMZEnDkbUvxhMmBYSdETk1rRgm+R4LOzFUGaHqHDLKLX+FIPKcF96hrucXzcWyLbIbEgE98OHlnVYCzRdK8jlqm8tehUc9c9WhQ== vagrant insecure public key'

install -d -m 0700 -o vagrant -g vagrant /home/vagrant/.ssh
touch /home/vagrant/.ssh/authorized_keys
chmod 0600 /home/vagrant/.ssh/authorized_keys
chown vagrant:vagrant /home/vagrant/.ssh/authorized_keys
set +e
grep -Fqx "$VAGRANT_PUBLIC_KEY" /home/vagrant/.ssh/authorized_keys
grep_status=$?
set -e
case "$grep_status" in
  0) ;;
  1) printf '%s\n' "$VAGRANT_PUBLIC_KEY" >> /home/vagrant/.ssh/authorized_keys ;;
  *) exit "$grep_status" ;;
esac
