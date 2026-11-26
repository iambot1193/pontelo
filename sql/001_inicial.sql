-- ponytail: migrations via docker-entrypoint-initdb.d (roda só em banco vazio).
-- Runner próprio quando existir 002.

CREATE TABLE credencial (
    provedor      text NOT NULL,          -- 'ml' | 'bling'
    conta         text NOT NULL,
    access_token  bytea NOT NULL,         -- Fernet
    refresh_token bytea NOT NULL,         -- Fernet
    expira_em     timestamptz NOT NULL,
    PRIMARY KEY (provedor, conta)
);

CREATE TABLE evento_webhook (
    id          text PRIMARY KEY,         -- topic+resource+sent
    recebido_em timestamptz NOT NULL DEFAULT now(),
    payload     jsonb                     -- apagar após 30 dias (LGPD)
);

CREATE TABLE vinculo_pedido (
    pedido_ml  text PRIMARY KEY,
    pedido_erp text NOT NULL,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mapa_sku (
    sku_ml      text PRIMARY KEY,
    item_ml     text NOT NULL,
    produto_erp text NOT NULL
);

CREATE TABLE tarefa_morta (
    id        bigserial PRIMARY KEY,
    tarefa    text NOT NULL,
    erro      text NOT NULL,
    tentativas int NOT NULL,
    morta_em  timestamptz NOT NULL DEFAULT now()
);
