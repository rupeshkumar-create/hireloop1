#!/usr/bin/env bash
# Fix hireschema.com apex DNS on Vercel (removes Google AAAA records that break HTTPS).
#
# Prereq: vercel login && vercel link (team that owns hireschema.com)
#
# Usage: ./scripts/fix-hireschema-dns.sh

set -euo pipefail

DOMAIN="hireschema.com"
APEX_A="76.76.21.21"

echo "==> DNS records for ${DOMAIN}"
vercel dns ls "$DOMAIN" || { echo "Run: vercel login"; exit 1; }

echo ""
echo "==> Remove stale AAAA records and apex A records pointing at Google (216.239.x.x)"
while read -r id _rest; do
  [[ -z "${id:-}" ]] && continue
  echo "    removing record id=${id}"
  vercel dns remove "$id" -y || true
done < <(vercel dns ls "$DOMAIN" 2>/dev/null | awk '/AAAA|216\.239\.|2\.57\.91\.91/{print $1}')

echo ""
echo "==> Ensure apex A -> ${APEX_A}"
vercel dns add "$DOMAIN" "@" A "$APEX_A" 2>/dev/null || echo "    (apex A may already exist)"

echo ""
echo "==> Done. Verify:"
echo "    dig hireschema.com A +short"
echo "    dig hireschema.com AAAA +short   # should be empty"
echo "    curl -sI https://hireschema.com | head -5"
