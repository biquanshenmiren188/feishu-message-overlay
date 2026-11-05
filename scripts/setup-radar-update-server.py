#!/usr/bin/env python3
"""Run as root after installing receiver and generating the root-only signing key.
Adds a static endpoint independent of website release symlinks. No backend restart.
"""
import os
from pathlib import Path
import shutil
import subprocess
import time

def main():
    root=Path('/var/lib/radar-desktop-updates')
    root.mkdir(exist_ok=True, mode=0o755)
    config=Path('/etc/nginx/conf.d/leida-shenmiren.conf')
    snippet=Path('/etc/nginx/snippets/radar-desktop-updates.conf')
    include=' include /etc/nginx/snippets/radar-desktop-updates.conf;'
    text=config.read_text()
    anchor=' ssl_protocols TLSv1.2 TLSv1.3;'
    if include not in text and text.count(anchor)!=1:
        raise RuntimeError('Unexpected nginx baseline')
    backup=Path('/var/backups/radar-desktop-updates-'+str(time.time_ns()))
    backup.mkdir(mode=0o700)
    shutil.copy2(config,backup/'nginx.conf')
    old_snippet=snippet.read_bytes() if snippet.exists() else None
    snippet.write_text('''location = /desktop-updates/latest.json {
 alias /var/lib/radar-desktop-updates/latest.json;
 default_type application/json;
 add_header Cache-Control "no-store, max-age=0" always;
 add_header X-Content-Type-Options "nosniff" always;
}
location ^~ /desktop-updates/ {
 alias /var/lib/radar-desktop-updates/;
 autoindex off;
 # Hide staging, lock files and directory requests even if a name is guessed.
 if ($uri ~ "(^|/)\\.") { return 404; }
 if ($uri ~ "/$") { return 404; }
 add_header Cache-Control "public, max-age=31536000, immutable";
 add_header X-Content-Type-Options "nosniff" always;
}
''')
    if include not in text:
        config.write_text(text.replace(anchor,anchor+'\n'+include))
    try:
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
    except Exception:
        shutil.copy2(backup/'nginx.conf',config)
        if old_snippet is None: snippet.unlink(missing_ok=True)
        else: snippet.write_bytes(old_snippet)
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        raise
    print('Nginx backup:',backup)

if __name__=='__main__': main()
