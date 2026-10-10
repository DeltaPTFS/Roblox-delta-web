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
cp website/static/community.css dist/style.css
if [ -d website/static/gallery ]; then cp -R website/static/gallery dist/gallery; fi
cp website/static/delta-emblem.svg dist/favicon.svg
discord_invite="${DISCORD_INVITE_URL:-https://discord.gg/}"
escaped_discord=$(printf '%s' "$discord_invite" | sed 's/[&|]/\\&/g')
sed -e "s|__SKYMILES_BACKEND_URL__|$escaped_url|g" -e "s|__DISCORD_INVITE_URL__|$escaped_discord|g" static-site/index.html > dist/index.html

if grep -q '__SKYMILES_BACKEND_URL__' dist/index.html; then
  echo "Static-site backend placeholder was not replaced" >&2
  exit 1
fi
