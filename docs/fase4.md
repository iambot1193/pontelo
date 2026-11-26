# Fase 4: sua parte (manual)

Comandos rodam na pasta `D:\dev\pontelo`, com o Docker ligado.

## Onde paramos (2026-11-26)

| Item | Situação |
|------|----------|
| Código fases 1–3 e 5 | Pronto. Lint limpo, 26 testes passando (`docker compose run --rm testes`) |
| Bling: app + OAuth | Conectado. Token salvo cifrado no Postgres e renovado sozinho |
| Bling: escopos | Pedidos de Venda (ler + gerenciar), Estoques (ler). **Sem excluir**: a integração não precisa |
| Bling: leitura real | OK: forma de pagamento (Pix), pedidos, saldos de estoque |
| Bling: criar pedido real | **OK**: `TESTE-PONTELO-1795717157` criado; a 2ª chamada achou o mesmo, sem duplicar |
| Mercado Livre: app | **Aguardando aprovação** do formulário (uso pessoal; Manage sales + Manage product listings) |
| ML: OAuth, webhook, pedido de ponta a ponta | Não testado: depende do app aprovado |

**Pendências soltas:**
- [ ] Apagar à mão o pedido `TESTE-PONTELO-1795717157` no Bling (Vendas → Pedidos de venda).
- [ ] Commit (ainda não feito; peça quando quiser).

**Riscos conhecidos para quando o ML chegar:**
- Troca de token no ML: o código manda client_id/secret no corpo **e** no cabeçalho Basic.
  Se o ML recusar (`invalid_client`), o ajuste é de 1 linha em `app/oauth.py` (tirar o `auth=`).
- O vendedor conectado precisa ser o **vendedor de teste**. Senão o webhook chega com outro
  `user_id` e é ignorado de propósito (`app/webhooks.py`).
- Anúncio **com variações** não tem estoque atualizado (limite conhecido, README).

## Retomar quando o ML aprovar

Cada passo depende do anterior.

### 1. Túnel
```
sh scripts/tunel.sh
```
Deixe o terminal aberto. A URL muda a cada início. Ele mostra as URLs para colar:
- Bling → app pontelo → link de redirecionamento: `<túnel>/callback/bling`
  (o token atual não depende disso; só serve para reconectar)
- ML → app → URI de redirect: `<túnel>/callback/ml`
- ML → app → URL de notificações: `<túnel>/webhooks/ml`, tópico **Orders (`orders_v2`)**

### 2. Configurar o app do ML (DevCenter)
developers.mercadolivre.com.br/devcenter → seu app → editar:
- Redirect e notificações: as do passo 1.
- PKCE: **desligado** (o código não usa).
- Escopos: leitura, escrita e `offline_access` (sem ele não vem o refresh token).
- Copiar **Client ID** e **Client Secret**.

### 3. Credenciais
No `.env`:
```
ML_CLIENT_ID=<client id>
ML_CLIENT_SECRET=<client secret>
```
As URLs reais do ML já estão lá. Depois:
```
docker compose up -d --force-recreate api worker
```

### 4. Conectar sua conta real
Abrir `<túnel>/conectar/ml` e autorizar. A resposta esperada é `{"conectado":"ml"}`.

### 5. Usuários de teste
Rodar **2 vezes**, uma para o vendedor e outra para o comprador:
```
docker compose exec api python -m scripts.ml_usuario_teste
```
Guarde o login e a senha de cada um. O ML não mostra de novo.

### 6. Conectar o vendedor de teste
Numa aba anônima, entrar no ML como o **vendedor de teste** e abrir `<túnel>/conectar/ml` de novo.

### 7. Anúncio
Ainda como vendedor de teste: criar 1 anúncio **sem variações**, com SKU `SKU-1` e estoque 5.
Anotar o código `MLB...` (está na URL).

### 8. Mapa de SKU
Abrir `<túnel>/admin`. O usuário pode ser qualquer um; a senha é o `ADMIN_SENHA` do `.env`.
Em "Mapa de SKU", preencher:
- SKU: `SKU-1`
- `MLB...` do anúncio
- id do produto no Bling: está na URL da tela do produto. Crie um produto no Bling se não tiver.

### 9. Testar de ponta a ponta
- Conexões: `docker compose exec api python -m scripts.verificar`. Bling e ML devem aparecer com OK.
- Pedido: numa aba anônima, entrar como **comprador de teste** e comprar o anúncio.
  Acompanhar com `docker compose logs -f worker`. O pedido aparece no Bling em segundos.
- Estoque: mudar o estoque do produto no Bling. Em até 5 min o anúncio muda.
- Conciliação: fechar o túnel, comprar de novo e reabrir. O pedido entra em até 1 h
  (ou rode `docker compose restart worker` para conciliar na hora).
- Falha: o `/admin` mostra a fila de mortos com o botão reprocessar.

### 10. Fechar
- Vídeo de 1 min: compra no ML, pedido no Bling, painel. Só contas de teste.
- Commit (o `.env` não entra; está no `.gitignore`).

## Comandos úteis
| Para | Comando |
|------|---------|
| Subir tudo | `docker compose up -d --build api worker falsos` |
| Testes + lint | `docker compose run --rm testes sh -c "ruff check . && pytest -q -p no:warnings"` |
| Checar contas (só leitura) | `docker compose exec api python -m scripts.verificar` |
| Pedido real de teste no Bling | `docker compose exec api python -m scripts.teste_bling [id_produto] [--manter]` |
| Logs do worker | `docker compose logs -f worker` |
| Reconectar Bling | `<túnel>/conectar/bling` |

## Se algo falhar
Mande a mensagem de erro exata. O que já conhecemos:

| Erro | Causa e correção |
|------|------------------|
| `403 insufficient_scope` (Bling) | Falta escopo no app. Marcar o escopo no app do Bling e **reconectar** em `/conectar/bling`: o token guarda os escopos antigos |
| Bling token com 301/404 | Trocar `BLING_TOKEN_URL` para `https://bling.com.br/Api/v3/oauth/token` |
| ML `invalid_client` na troca de token | Tirar o cabeçalho Basic em `app/oauth.py` |
| ML `redirect_uri mismatch` | O túnel mudou. Atualizar o redirect no DevCenter |
| Pedido não chega | Ver `docker compose logs api` (o webhook chegou?) e o `/admin` (fila de mortos). A conciliação horária pega o que faltar |
| `.env` mudou e nada aconteceu | `docker compose up -d --force-recreate api worker` |

A demo com APIs falsas (`scripts/demo.sh`) só funciona com o `.env.bak`, que tem as URLs falsas.
Os testes usam banco `_teste` e Redis db 15 isolados, então não apagam o token real.
