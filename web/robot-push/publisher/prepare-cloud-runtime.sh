#!/bin/bash
# Preparation only. Does not start or enable a Feishu long connection.
set -euo pipefail
stage=${1:?Pass the staged bridge directory}
test "$(uname -m)" = x86_64
root=/opt/robot-push
version=v22.23.3
archive=node-${version}-linux-x64.tar.xz
expected=df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de
if ! test -x "$root/node/bin/node"; then
  scratch=$(mktemp -d)
  trap 'rm -rf -- "$scratch"' EXIT
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 "https://nodejs.org/dist/${version}/${archive}" -o "$scratch/$archive"
  printf '%s  %s\n' "$expected" "$scratch/$archive" | sha256sum -c -
  tar -xJf "$scratch/$archive" -C "$scratch"
  mv "$scratch/node-${version}-linux-x64" "$root/node"
fi
test "$("$root/node/bin/node" --version)" = "$version"
install -d -m 755 "$root/cloud-bridge"
cp "$stage/"*.mjs "$stage/package.json" "$stage/package-lock.json" "$root/cloud-bridge/"
cd "$root/cloud-bridge"
PATH="$root/node/bin:$PATH" npm ci --ignore-scripts --omit=dev --no-audit --no-fund
"$root/node/bin/node" --check cloud-main.mjs
printf 'CLOUD_RUNTIME_PREPARED_NOT_STARTED\n'
