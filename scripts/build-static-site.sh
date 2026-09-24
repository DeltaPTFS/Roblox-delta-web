#!/bin/sh
set -eu

backend_url="${SKYMILES_BACKEND_URL:-https://roblox-delta-web.onrender.com}"
case "$backend_url" in
  https://*) ;;
  *) echo "SKYMILES_BACKEND_URL must begin with https://" >&2; exit 1 ;;
esac

backend_url="${backend_url%/}"
escaped_url=$(printf '%s' "$backend_url" | sed 's/[&|]/\\&/g')
rm -rf dist
mkdir -p dist
cp static-site/style.css dist/style.css
cp website/static/delta-emblem.svg dist/favicon.svg
sed "s|__SKYMILES_BACKEND_URL__|$escaped_url|g" static-site/index.html > dist/index.html

if grep -q '__SKYMILES_BACKEND_URL__' dist/index.html; then
  echo "Static-site backend placeholder was not replaced" >&2
  exit 1
fi
