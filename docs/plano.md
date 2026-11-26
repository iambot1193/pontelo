# Plano: pontelo

Esforço total: **25–35 h** (~3 semanas no ritmo de 12 h/semana).

## 0. Antes de codar (verificar, ~2 h)
Nada abaixo foi confirmado. Anotar a resposta aqui antes de decidir.

| Pergunta | Por que importa | Se falhar |
|----------|-----------------|-----------|
| Bling API v3 tem conta de teste ou trial gratuito com API liberada? Por quanto tempo? | Sem conta não há demo real | Tiny/Olist ou Omie; ou só o ERP falso (ver 2.3) |
| Mercado Livre: criar usuário de teste pela API (`/users/test_user`) ainda funciona? Limite de quantos? | Vender/comprar sem dinheiro real | Usar só o ML falso + gravações de respostas reais da documentação |
| Quais tópicos de notificação do ML cobrem pedido e estoque (`orders_v2`, `items`, `stock-locations`)? | Define o que o webhook recebe | Conciliação por polling cobre |
| Webhook do ML exige HTTPS público? | Precisa de túnel na demo | Cloudflare Tunnel (já usado no trabalho) ou Tailscale Funnel |
| Limites de requisição de cada API | Configura o limitador | Valor conservador + tratar 429 |

**Regra:** o projeto nasce com **APIs falsas** (ver 2.3). As contas reais só entram na
fase 4. Se o trial não existir, o projeto continua completo e honesto: README diz
"testado contra simulador + contas de teste do ML".

## 1. Fluxos

### 1.1 Pedido ML → ERP
```
ML vende ─► POST /webhooks/ml {topic: orders_v2, resource: /orders/123}
   grava evento (id único = topic+resource+sent) → já existe? 200 e para
   responde 200 em < 500 ms; enfileira "importar_pedido:123"
worker ─► GET /orders/123 (token ML) ─► mapeia itens (SKU ML ↔ produto ERP)
        ─► POST pedido no ERP  (chave de idempotência = id do pedido ML)
        ─► grava vínculo pedido_ml ↔ pedido_erp
```
Sem SKU mapeado: o pedido vai para "pendente de mapeamento" com alerta, não falha calado.

### 1.2 Estoque ERP → ML
```
ERP muda estoque ─► webhook do ERP (se houver) ou polling a cada 5 min
   enfileira "estoque:SKU" (dedupe: só o último valor importa)
worker ─► PUT /items/{id} available_quantity
```
Conflito: **o ERP é a fonte da verdade do estoque**, o ML é a do pedido. Escrito no
README, sem lógica de "quem ganha".

### 1.3 Conciliação (a cada hora)
Lista os pedidos do ML das últimas 48 h e confere com a tabela de vínculos. Os que
faltarem entram na fila. É o que garante "nenhum pedido perdido" mesmo com webhook
caído ou PC desligado.

## 2. Componentes

### 2.1 OAuth (`app/oauth.py`)
- Fluxo authorization code: `/conectar/ml` e `/conectar/bling` → callback → tokens.
- Tabela `credencial(provedor, conta, access_token, refresh_token, expira_em)`,
  **tokens cifrados** (Fernet, chave no `.env`).
- Renovar quando faltar < 10 min ou ao receber 401 (uma vez só, depois alerta).
- Trava por provedor na renovação (`SELECT ... FOR UPDATE`): dois workers não
  renovam juntos. O refresh token do ML é de uso único, e renovar duas vezes invalida a conta.

### 2.2 Fila (`app/fila.py`)
- Redis: lista principal + conjunto ordenado para os agendados (retentativa no futuro).
- Retentativa: 30 s, 2 min, 10 min, 1 h, 6 h → **fila de mortos** + alerta Telegram.
- Erro 4xx de dado (SKU inválido) não repete: vai direto para mortos. 5xx/429/rede repete.
- `GET /admin/mortos` + botão reprocessar.
- *ponytail: fila própria de ~60 linhas em vez de Celery/RQ. Trocar por RQ se precisar
  de vários workers com prioridade.*

### 2.3 APIs falsas (`tests/falsos/`)
Duas apps FastAPI pequenas imitando ML e Bling (só as rotas usadas), com modo
"falhar": 429, 500, timeout, token vencido. São a base dos testes e da demo sem conta.
Respostas copiadas do formato da documentação oficial, com dados inventados.

### 2.4 ERP por adaptador (`app/erp/`)
Contrato: `criar_pedido`, `buscar_estoque(sku)`, `listar_estoque_alterado(desde)`.
`bling.py` primeiro. `tiny.py` só se sobrar tempo, mas o contrato já prova a troca.

### 2.5 Observabilidade
- Log estruturado (JSON) com `correlacao_id` do evento ao pedido no ERP.
- `GET /admin` simples: pedidos hoje, fila, mortos, último sucesso por provedor, token
  expira em. HTML puro, sem framework.
- Alerta Telegram: fila de mortos, token não renovou, conciliação achou falta.
  (Mesmo código de envio do extra 1 do dumpbox: copiar, não depender.)

## 3. Banco (Postgres)
`credencial`, `evento_webhook(id único, recebido_em, payload)`, `vinculo_pedido`,
`mapa_sku`, `tarefa_morta`. Migrações em SQL puro numeradas (`sql/001_inicial.sql`).

## 4. Fases

| Fase | Entrega | Horas |
|------|---------|-------|
| 1 | Compose (api, worker, postgres, redis), APIs falsas, OAuth contra o falso | 6–8 |
| 2 | Fluxo pedido ML→ERP com webhook idempotente + fila + retentativa | 8–10 |
| 3 | Estoque ERP→ML, conciliação, painel admin, alertas | 6–8 |
| 4 | Contas reais de teste (ML + Bling), túnel HTTPS, vídeo de 1 min | 3–5 |
| 5 | README final: diagrama, números dos testes de falha, limites conhecidos | 2–3 |

## 5. Testes (o diferencial)
- **Idempotência:** o mesmo webhook 5 vezes dá 1 pedido no ERP.
- **Falha:** ERP devolve 500 três vezes e depois 200, e o pedido entra uma vez só.
- **429:** o limitador espera o `Retry-After`, sem estourar.
- **Token:** vence no meio do lote, renova uma vez e o lote continua.
- **Concorrência:** 2 workers e 50 pedidos, sem duplicata e com uma renovação só.
- **Conciliação:** webhook "perdido" de propósito, o pedido aparece na próxima hora.
Rodar com `docker compose run --rm testes`. Números (ex.: "1.000 eventos com 20% de
falha injetada, 0 duplicados, 0 perdidos") vão para o README.

## 6. Segurança e LGPD
- Tokens cifrados no banco. `.env` fora do Git, com `.env.example` no lugar.
- Webhook do ML: conferir `application_id` e `user_id` do aviso contra a conta conectada.
- Payload de pedido tem nome e endereço do comprador: guardar só o necessário e
  apagar o `payload` bruto depois de 30 dias.
- Nada de dado real no repositório. Prints e vídeo só com contas de teste.

## 7. Fora de escopo
Multi-loja/multiempresa, nota fiscal, preço/anúncio (só estoque), n8n (dá para
mostrar o mesmo fluxo depois como comparação), Shopee/Amazon (o contrato de
adaptador já indica o caminho), front-end além do painel admin.

## 8. Currículo (só depois de pronto)
- "pontelo: integrador Mercado Livre ↔ ERP com OAuth, webhooks idempotentes e fila com
  retentativa; testado com falhas injetadas (0 pedidos duplicados ou perdidos em N eventos)."
- Freelance: link + vídeo. Responde direto às vagas de "integrar Bling/ML".
