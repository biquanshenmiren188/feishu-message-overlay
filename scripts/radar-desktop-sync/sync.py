#!/usr/bin/env python3
"""Mirror the public desktop release into the existing signed radar feed."""
import base64
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen


REPO = "biquanshenmiren188/feishu-message-overlay"
API = f"https://api.github.com/repos/{REPO}"
LATEST = Path("/var/lib/radar-desktop-updates/latest.json")
RECEIVER = "/usr/local/sbin/radar-update-receiver"
MAX_SIZE = 256 * 1024 * 1024


def version(tag):
    if not re.fullmatch(r"v[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]{1,6}", tag):
        raise ValueError("Unexpected desktop version")
    parts = tuple(map(int, tag[1:].split(".")))
    datetime.date(*parts[:3])
    return parts


def api(path):
    request = Request(API + path, headers={"User-Agent": "radar-desktop-sync"})
    with urlopen(request, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Oversized GitHub metadata")
    return json.loads(data)


def fetch(current, output):
    release = api("/releases/latest")
    tag = release["tag_name"]
    if release["draft"] or release["prerelease"]:
        raise ValueError("Official desktop release required")
    target_version = version(tag)
    if current and target_version < version(current["Version"]):
        return
    names = {f"FeishuMessageOverlay-{tag}-win-x64.zip", "FeishuMessageOverlay-win-x64.zip"}
    assets = [a for a in release["assets"] if a["name"] in names]
    if len(assets) != 1:
        raise ValueError("Missing or ambiguous Windows package")
    asset = assets[0]
    url = f"https://github.com/{REPO}/releases/download/{tag}/{asset['name']}"
    digest = asset.get("digest") or ""
    if (asset["state"] != "uploaded" or asset["browser_download_url"] != url
            or not re.fullmatch("sha256:[0-9a-f]{64}", digest)
            or not 0 < asset["size"] <= MAX_SIZE):
        raise ValueError("Invalid GitHub release asset")
    commit = api("/commits/" + tag)["sha"]
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("Invalid tag commit")
    meta = dict(Version=tag, SourceCommit=commit, Size=asset["size"], Sha256=digest[7:])
    if current and tag == current["Version"]:
        if any(current[k] != v for k, v in meta.items()):
            raise ValueError("Published release changed")
        print(f"Radar already has {tag}", file=sys.stderr)
        return
    output.write(json.dumps(meta).encode() + b"\n")
    checksum = hashlib.sha256()
    remaining = meta["Size"]
    with urlopen(url, timeout=60) as response:
        while remaining:
            block = response.read(min(remaining, 1024 * 1024))
            if not block:
                raise ValueError("Truncated release asset")
            checksum.update(block)
            output.write(block)
            remaining -= len(block)
        if response.read(1) or checksum.hexdigest() != meta["Sha256"]:
            raise ValueError("Release asset checksum or size mismatch")


def sync():
    # Only the preinstalled receiver needs the signing key. The network client
    # runs as nobody and writes to an anonymous file held by this process.
    with tempfile.TemporaryFile() as candidate:
        subprocess.run([sys.executable, "-I", __file__, "--fetch"], check=True,
                       user="nobody", group="nogroup", extra_groups=[], stdout=candidate)
        if candidate.tell():
            candidate.seek(0)
            subprocess.run([RECEIVER], stdin=candidate, check=True, timeout=600)


if __name__ == "__main__":
    if sys.argv[1:] == ["--fetch"]:
        current = None
        if LATEST.exists():
            current = json.loads(base64.b64decode(json.loads(LATEST.read_bytes())["payload"]))
        fetch(current, sys.stdout.buffer)
    elif not sys.argv[1:]:
        sync()
    else:
        sys.exit("Unexpected arguments")
