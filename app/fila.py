"""Fila em Redis: lista principal + zset de agendadas + tabela de mortos no Postgres.

Tarefa = "nome:arg" (ex.: "importar_pedido:123").
Tarefa em execução fica em uma lista de processamento por host (LMOVE): se o worker
morrer no meio, recuperar() na partida devolve à fila. Handlers são idempotentes.
"""
import json
import logging
import socket
import time

import redis

from app import alerta, config, db
from app.http import ErroPermanente

r = redis.from_url(config.REDIS_URL, decode_responses=True)
FILA, AGENDADAS = "pontelo:fila", "pontelo:agendadas"
PROCESSANDO = f"pontelo:processando:{socket.gethostname()}"
ATRASOS = [30, 120, 600, 3600, 21600]  # 30 s, 2 min, 10 min, 1 h, 6 h
log = logging.getLogger("fila")


def enfileirar(tarefa: str, tentativa: int = 0, atraso: float = 0):
    item = json.dumps({"t": tarefa, "n": tentativa})
    if atraso:
        r.zadd(AGENDADAS, {item: time.time() + atraso})
    else:
        r.lpush(FILA, item)


def recuperar() -> int:
    """Devolve à fila o que este host deixou pela metade. Chamar só na partida do worker."""
    n = 0
    while r.lmove(PROCESSANDO, FILA, "RIGHT", "RIGHT"):
        n += 1
    return n


def _liberar_agendadas(agora: float):
    for item in r.zrangebyscore(AGENDADAS, 0, agora):
        if r.zrem(AGENDADAS, item):  # quem remove primeiro, leva
            r.lpush(FILA, item)


def _morta(tarefa: str, erro: str, tentativas: int):
    with db.conectar() as conn:
        conn.execute("INSERT INTO tarefa_morta (tarefa, erro, tentativas) VALUES (%s, %s, %s)",
                     (tarefa, erro[:2000], tentativas))
    alerta.enviar(f"tarefa morta: {tarefa} ({tentativas} tentativas): {erro[:300]}")


def _executar(handlers: dict, d: dict):
    nome, _, arg = d["t"].partition(":")
    n = d["n"] + 1
    if nome not in handlers:
        return _morta(d["t"], "handler desconhecido", n)
    try:
        handlers[nome](arg)
        log.info(json.dumps({"correlacao_id": d["t"], "ok": True, "tentativa": n}))
    except ErroPermanente as e:
        _morta(d["t"], str(e), n)
    except Exception as e:  # 5xx, 429 esgotado, rede, bug
        log.warning(json.dumps({"correlacao_id": d["t"], "erro": repr(e), "tentativa": n}))
        if n > len(ATRASOS):
            _morta(d["t"], repr(e), n)
        else:
            enfileirar(d["t"], n, ATRASOS[n - 1])


def processar_pendentes(handlers: dict, agora: float | None = None) -> int:
    """Processa tudo que está pronto. Devolve quantas tarefas rodou."""
    _liberar_agendadas(agora or time.time())
    feitas = 0
    while item := r.lmove(FILA, PROCESSANDO, "RIGHT", "LEFT"):
        _executar(handlers, json.loads(item))
        r.lrem(PROCESSANDO, 1, item)
        feitas += 1
    return feitas


def disparar_periodica(tarefa: str, intervalo: int):
    """Enfileira no máximo uma vez por intervalo, mesmo com vários workers."""
    if r.set(f"pontelo:periodica:{tarefa}", "1", nx=True, ex=intervalo):
        enfileirar(f"{tarefa}:")


def reprocessar(id_morta: int):
    with db.conectar() as conn:
        linha = conn.execute("DELETE FROM tarefa_morta WHERE id = %s RETURNING tarefa",
                             (id_morta,)).fetchone()
    if linha:
        enfileirar(linha[0])
