import os
import pathlib

# Isolamento: testes NUNCA tocam o banco/Redis da stack nem as APIs reais.
# (Antes compartilhavam e o TRUNCATE apagou um token real.)
for k in [k for k in os.environ if k.startswith(("ML_", "BLING_"))]:
    del os.environ[k]
_base, _, _nome = os.environ["DATABASE_URL"].rpartition("/")
TESTE_DB = f"{_base}/{_nome}_teste"
os.environ["DATABASE_URL"] = TESTE_DB
os.environ["REDIS_URL"] = os.environ["REDIS_URL"].rsplit("/", 1)[0] + "/15"

import psycopg

with psycopg.connect(f"{_base}/{_nome}", autocommit=True) as _c:
    if not _c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (f"{_nome}_teste",)).fetchone():
        _c.execute(f'CREATE DATABASE "{_nome}_teste"')
        with psycopg.connect(TESTE_DB, autocommit=True) as _t:
            _t.execute((pathlib.Path(__file__).parent.parent / "sql" / "001_inicial.sql").read_text())

import pytest
from fastapi.testclient import TestClient

from app import db, fila, http
from tests.falsos import app as falsos

assert db.conectar().info.dbname.endswith("_teste"), "testes fora do banco de teste"


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    falsos.resetar()
    fila.r.flushdb()
    monkeypatch.setattr(http, "cliente", lambda: TestClient(falsos.app))
    monkeypatch.setattr(http.time, "sleep", lambda s: None)  # 429 sem esperar de verdade
    yield


@pytest.fixture
def conectado():
    from tests.test_oauth import conectar
    conectar("ml")
    conectar("bling")
    with db.conectar() as conn:
        conn.execute("INSERT INTO mapa_sku VALUES ('SKU-1', 'MLB100', '777')")


@pytest.fixture(autouse=True)
def banco_limpo():
    with db.conectar() as conn:
        conn.execute("TRUNCATE credencial, evento_webhook, vinculo_pedido, mapa_sku, tarefa_morta")
    yield
