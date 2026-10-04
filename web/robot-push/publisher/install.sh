#!/bin/bash
set -euo pipefail
stage=${1:?staging directory required}
test "$(id -u)" = 0
test -f "$stage/server.py"
test -f "$stage/publisher-public.pem"
test ! -e /etc/systemd/system/robot-push.service
test ! -e /etc/nginx/snippets/robot-push.conf
test ! -e /etc/nginx/conf.d/robot-push-rate.conf
backup=/opt/funding-radar-web/backups/robot-push-publisher-20261002
test ! -e "$backup"
mkdir -p "$backup"
cp -a /etc/nginx/conf.d/funding-radar.conf "$backup/funding-radar.conf"
cp -a /opt/funding-radar-web/current/robot-push/style.css "$backup/style.css"
getent passwd robot-push >/dev/null || useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin robot-push
install -d -o root -g robot-push -m 0750 /opt/robot-push /etc/robot-push
install -d -o robot-push -g www-data -m 2750 /var/lib/robot-push
install -o root -g robot-push -m 0640 "$stage/server.py" /opt/robot-push/server.py
install -o root -g robot-push -m 0640 "$stage/publisher-public.pem" /etc/robot-push/publisher-public.pem
install -o root -g root -m 0644 "$stage/robot-push.service" /etc/systemd/system/robot-push.service
systemctl daemon-reload
systemctl enable --now robot-push.service
for n in 1 2 3 4 5; do curl --fail --silent http://127.0.0.1:18883/health >/dev/null && break; sleep 1; done
curl --fail --silent http://127.0.0.1:18883/health >/dev/null
install -o root -g root -m 0644 "$stage/nginx-routes.conf" /etc/nginx/snippets/robot-push.conf
printf 'limit_req_zone $binary_remote_addr zone=robot_push_publish:1m rate=2r/s;\n' > /etc/nginx/conf.d/robot-push-rate.conf
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/conf.d/funding-radar.conf')
s=p.read_text();needle='include /etc/nginx/snippets/radar-reference-server.conf;'
assert s.count(needle)==1
assert s.index('listen 443 ssl')<s.index(needle)
p.write_text(s.replace(needle,needle+'\n    include /etc/nginx/snippets/robot-push.conf;'))
PY
if ! nginx -t; then
  cp -a "$backup/funding-radar.conf" /etc/nginx/conf.d/funding-radar.conf
  rm -- /etc/nginx/snippets/robot-push.conf /etc/nginx/conf.d/robot-push-rate.conf
  systemctl disable --now robot-push.service
  exit 1
fi
systemctl reload nginx
install -o root -g root -m 0644 "$stage/style.css" /opt/funding-radar-web/current/robot-push/style.css
printf 'ROBOT_PUBLISHER_INSTALL_OK\n'
systemctl is-active robot-push nginx radar-reference-fast price-monitor-worker
curl --fail --silent http://127.0.0.1:18883/health
printf '\n'
