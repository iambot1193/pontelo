#!/usr/bin/env sh
# Demo sem conta real: stack + APIs falsas. Uso: docker compose up -d --build api worker falsos && sh scripts/demo.sh
set -eu
API=${API:-http://localhost:8000}
FALSOS=${FALSOS:-http://localhost:9000}
SENHA=$(grep '^ADMIN_SENHA=' .env | cut -d= -f2-)

echo "1. conectar ML e Bling (OAuth contra o falso)"
curl -sfL "$API/conectar/ml" && echo
curl -sfL "$API/conectar/bling" && echo

echo "2. mapear SKU-1 -> anúncio MLB100 -> produto 777 no ERP"
curl -sf -o /dev/null -u "x:$SENHA" -d sku_ml=SKU-1 -d item_ml=MLB100 -d produto_erp=777 "$API/admin/sku"

echo "3. venda no ML + webhook enviado 3 vezes (ML repete aviso)"
ID=$(date +%s)
curl -sf -o /dev/null -X POST "$FALSOS/_demo/pedido/$ID"
for i in 1 2 3; do
  curl -sf -o /dev/null -H 'Content-Type: application/json' \
    -d "{\"_id\":\"aviso-$ID\",\"topic\":\"orders_v2\",\"resource\":\"/orders/$ID\",\"user_id\":999,\"application_id\":\"teste\",\"attempts\":$i}" \
    "$API/webhooks/ml"
done

echo "4. estoque no ERP muda para 7"
curl -sf -o /dev/null -X POST "$FALSOS/_demo/estoque/777?qtd=7"
docker compose exec -T redis redis-cli DEL pontelo:periodica:verificar_estoque >/dev/null  # não esperar 5 min

echo "5. aguardando worker..."
sleep 4
curl -sf "$FALSOS/_demo/estado"; echo
echo "Painel: $API/admin (usuário qualquer, senha do .env)"
