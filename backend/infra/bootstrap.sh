#!/bin/bash
# Called from CloudFormation UserData in /opt/vendorops, after creating backend/.env.
set -euo pipefail
cd /opt/vendorops
# Small synthetic corpus only. Swap is on the encrypted root EBS volume.
if [ ! -f /var/vendorops.swap ]; then
  fallocate -l 2G /var/vendorops.swap
  chmod 0600 /var/vendorops.swap
  mkswap /var/vendorops.swap
fi
if ! swapon --show=NAME --noheadings | grep -qx /var/vendorops.swap; then
  swapon /var/vendorops.swap
fi
if ! grep -q '^/var/vendorops.swap ' /etc/fstab; then
  printf '/var/vendorops.swap none swap sw 0 0\n' >> /etc/fstab
fi
export COMPOSE_PARALLEL_LIMIT=1
compose_version=v5.6.0
plugin_directory=/usr/local/lib/docker/cli-plugins
mkdir -p "$plugin_directory"
download_directory=$(mktemp -d)
trap 'rm -f "$download_directory/docker-compose-linux-x86_64" "$download_directory/docker-compose-linux-x86_64.sha256"; rmdir "$download_directory"' EXIT
release_url="https://github.com/docker/compose/releases/download/$compose_version"
curl --fail --silent --show-error --location "$release_url/docker-compose-linux-x86_64" --output "$download_directory/docker-compose-linux-x86_64"
curl --fail --silent --show-error --location "$release_url/docker-compose-linux-x86_64.sha256" --output "$download_directory/docker-compose-linux-x86_64.sha256"
(cd "$download_directory" && sha256sum --check docker-compose-linux-x86_64.sha256)
install -m 0755 "$download_directory/docker-compose-linux-x86_64" "$plugin_directory/docker-compose"
docker compose version
docker compose --env-file backend/.env -f backend/infra/compose.yaml -f backend/infra/compose.aws.yaml config --quiet
docker compose --env-file backend/.env -f backend/infra/compose.yaml -f backend/infra/compose.aws.yaml up --build --detach --wait --wait-timeout 180
curl --fail --silent --retry 30 --retry-connrefused --retry-delay 2 http://127.0.0.1:8000/health
curl --fail --silent --retry 30 --retry-connrefused --retry-delay 2 http://127.0.0.1:8501/_stcore/health
printf '\nVendorOps is ready. Live AWS calls and sending remain disabled.\n'
