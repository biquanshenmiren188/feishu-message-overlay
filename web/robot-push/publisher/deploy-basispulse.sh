#!/bin/sh
set -eu
# Run as root after staging only reviewed files and provisioning the secret separately.
stage=/tmp/basispulse-release-20261004
web=/opt/funding-radar-web/current/robot-push
backup=/opt/robot-push/backups/basispulse-20261004
test -f /etc/robot-push/basispulse.json
test ! -e "$backup"
echo '8233c4b368bba3bda4898321f88c5bd46e203a15426a331525038fe32d53e247  /opt/funding-radar-web/current/robot-push/index.html' | sha256sum -c -
mkdir -p "$backup"
cp "$web/index.html" "$backup/index.html"
cp /etc/nginx/snippets/robot-push.conf "$backup/robot-push.conf"
install -m 0644 "$stage/basispulse.py" /opt/robot-push/basispulse.py
install -m 0644 "$stage/basispulse.service" /etc/systemd/system/basispulse.service
for file in basispulse.js basispulse.css basispulse-model.js basispulse-card.js basispulse-card-model.js basispulse-transfers.js source-entry.js; do
  install -m 0644 "$stage/$file" "$web/$file"
done
cat >> /etc/nginx/snippets/robot-push.conf <<'NGINX'

# Same Cloudflare Access protection as the robot-push page; no new bypass policy.
location = /radar/robot-push/basispulse.json {
    limit_except GET { deny all; }
    alias /var/lib/robot-push/basispulse.json;
    default_type application/json;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options nosniff always;
    access_log off;
}
NGINX
if ! nginx -t; then
  cp "$backup/robot-push.conf" /etc/nginx/snippets/robot-push.conf
  exit 1
fi
systemctl daemon-reload
systemctl enable --now basispulse
systemctl reload nginx
install -m 0644 "$stage/index.html" "$web/index.html"
systemctl is-active basispulse robot-push
