#!/usr/bin/env bash
# Fix hireschema.com apex DNS on Vercel.
#
# Symptom in browser:
#   "Error: Server Error — The service you requested is not available yet.
#    Please try again in 30 seconds."
# That page is Google Frontend (stale apex records), NOT your Vercel app.
#
# Prereq: vercel login   (team that owns hireschema.com)
#
# Usage: ./scripts/fix-hireschema-dns.sh

set -euo pipefail

DOMAIN="hireschema.com"
APEX_A="76.76.21.21"

echo "==> Current DNS for ${DOMAIN}"
vercel dns ls "$DOMAIN" || { echo "Run: vercel login"; exit 1; }

echo ""
echo "==> Remove ALL apex AAAA records (Google IPv6 breaks HTTPS on many networks)"
while read -r id _rest; do
  [[ -z "${id:-}" ]] && continue
  echo "    removing AAAA id=${id}"
  vercel dns remove "$id" -y || true
done < <(vercel dns ls "$DOMAIN" 2>/dev/null | awk '/AAAA/{print $1}')

echo ""
echo "==> Remove apex A records pointing at Google (216.239.x.x / 216.198.x.x)"
while read -r id _rest; do
  [[ -z "${id:-}" ]] && continue
  echo "    removing A id=${id}"
  vercel dns remove "$id" -y || true
done < <(vercel dns ls "$DOMAIN" 2>/dev/null | awk '/ A / && /216\.(239|198)\./{print $1}')

echo ""
echo "==> Ensure exactly one apex A -> ${APEX_A} (Vercel)"
if vercel dns ls "$DOMAIN" 2>/dev/null | awk -v ip="$APEX_A" '/ A / && $0 ~ ip {found=1} END{exit !found}'; then
  echo "    apex A ${APEX_A} already present"
else
  vercel dns add "$DOMAIN" "@" A "$APEX_A"
fi

echo ""
echo "==> Done. Verify (wait 1–2 min for propagation):"
echo "    dig hireschema.com A +short        # expect: ${APEX_A}"
echo "    dig hireschema.com AAAA +short     # expect: (empty)"
echo "    curl -4 -sI https://hireschema.com | head -3   # expect: HTTP/2 308 + location www"
