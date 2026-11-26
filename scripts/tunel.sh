#!/usr/bin/env sh
# Abre túnel HTTPS, grava BASE_URL no .env, recria api/worker e mostra as URLs para colar nos apps.
# Uso: sh scripts/tunel.sh   (deixe o terminal aberto; Ctrl+C fecha o túnel)
set -eu
CF="${CLOUDFLARED:-/c/Program Files (x86)/cloudflared/cloudflared}"
LOG=$(mktemp)
"$CF" tunnel --no-autoupdate --url http://localhost:8000 >"$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT INT TERM
URL=""
for _ in $(seq 1 60); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -z "$URL" ] && { echo "túnel não subiu:"; tail -5 "$LOG"; exit 1; }
sed -i "s|^BASE_URL=.*|BASE_URL=$URL|" .env
docker compose up -d --force-recreate api worker >/dev/null 2>&1
echo
echo "Túnel: $URL"
echo "Cole nos apps (só muda se o túnel reiniciar):"
echo "  Bling redirect:     $URL/callback/bling"
echo "  ML redirect:        $URL/callback/ml"
echo "  ML notificações:    $URL/webhooks/ml"
echo "Conectar:  $URL/conectar/bling   $URL/conectar/ml"
echo "Painel:    $URL/admin"
wait $PID
