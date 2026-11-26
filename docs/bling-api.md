# Bling API v3: o que o pontelo usa

Fonte: especificação OpenAPI oficial (developer.bling.com.br), conferida em 2026-11-26.

| Item | Valor |
|------|-------|
| Base | `https://api.bling.com.br/Api/v3` |
| Autorização | `https://www.bling.com.br/Api/v3/oauth/authorize` (link de convite do app) |
| Token | spec diz `https://bling.com.br/Api/v3/oauth/token`; usamos `www.` (mesmo host da autorização). Se falhar com 301/404, trocar no `.env`. |
| Credenciais no token | spec não diz; enviamos Basic **e** corpo |
| Buscar pedido por número do ML | `GET /pedidos/vendas?numerosLojas[]=<id ML>` |
| Criar pedido | `POST /pedidos/vendas` → 201 `{data:{id}}`. Obrigatórios: `contato.id`, `data`, `dataPrevista`, `dataSaida`, `itens[].{descricao,quantidade,valor}`, `parcelas[]` (com `formaPagamento.id`) |
| Saldo | `GET /estoques/saldos?idsProdutos[]=...` (máx. 100) → `data[].produto.id`, `saldoVirtualTotal` |
| Pegadinha | `filtroSaldoEstoque` padrão `1` = **só saldo positivo**. Produto zerado some da resposta; tratamos ausente como 0. |
| Webhook de estoque | existe (tela Webhooks do app). Não usado ainda; polling 5 min cobre. |

Não está na spec: limite de requisições. 429 tratado com `Retry-After`.
