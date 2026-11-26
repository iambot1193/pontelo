import json
import os
import random
import threading

from fastapi.testclient import TestClient

from app import db, fila, oauth
from app.main import app
from app.worker import HANDLERS
from tests.falsos import app as falsos
from tests.test_pedidos import aviso, rodar_ate_esvaziar

api = TestClient(app)
SENHA = ("x", "s3gredo")


def test_worker_morto_no_meio_recupera(conectado):
    falsos.pedido_ml_exemplo("123")
    fila.enfileirar("importar_pedido:123")
    fila.r.lmove(fila.FILA, fila.PROCESSANDO, "RIGHT", "LEFT")  # pegou a tarefa e "morreu"
    assert fila.processar_pendentes(HANDLERS) == 0
    assert fila.recuperar() == 1
    rodar_ate_esvaziar()
    assert "123" in falsos.estado["pedidos_erp"]
    assert fila.r.llen(fila.PROCESSANDO) == 0


def test_periodica_dispara_uma_vez_com_varios_workers():
    for _ in range(5):
        fila.disparar_periodica("conciliar", 3600)
    assert fila.r.llen(fila.FILA) == 1


def test_webhook_de_outra_conta_ml_ignorado(conectado):
    assert fila.r.get(oauth.ML_USER_ID) == "999"
    assert api.post("/webhooks/ml", json={**aviso(), "user_id": 1}).json() == {"ignorado": "user_id"}


def test_reenvio_com_mesmo_id_deduplica(conectado):
    falsos.pedido_ml_exemplo("123")
    for tentativa in range(1, 4):  # ML reenvia: mesmo _id, sent diferente
        api.post("/webhooks/ml", json={**aviso(sent=f"t{tentativa}"), "_id": "aviso-1", "attempts": tentativa})
    assert fila.r.llen(fila.FILA) == 1


def test_state_oauth_uso_unico():
    c = TestClient(app, follow_redirects=False)
    state = c.get("/conectar/ml").headers["location"].split("state=")[1]
    assert c.get("/callback/ml", params={"code": "codigo-ml", "state": state}).status_code == 200
    assert c.get("/callback/ml", params={"code": "codigo-ml", "state": state}).status_code == 400


def test_admin_cadastra_sku(conectado, monkeypatch):
    monkeypatch.setenv("ADMIN_SENHA", SENHA[1])
    api.post("/admin/sku", auth=SENHA, data={"sku_ml": "SKU-2", "item_ml": "MLB2", "produto_erp": "888"})
    with db.conectar() as conn:
        assert conn.execute("SELECT item_ml, produto_erp FROM mapa_sku WHERE sku_ml = 'SKU-2'").fetchone() == ("MLB2", "888")
    assert "SKU-2" in api.get("/admin", auth=SENHA).text


def test_carga_com_falha_injetada(conectado):
    """N pedidos, cada aviso 1-3 vezes, 20% das chamadas falham (500/503/429), 2 workers."""
    n = int(os.environ.get("CARGA_N", "200"))
    random.seed(42)
    for i in range(1, n + 1):
        falsos.pedido_ml_exemplo(str(i))
    falsos.estado["taxa_falha"] = 0.2
    for i in range(1, n + 1):
        for _ in range(random.randint(1, 3)):
            api.post("/webhooks/ml", json=aviso(str(i)))
    ts = [threading.Thread(target=rodar_ate_esvaziar) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    falsos.estado["taxa_falha"] = 0
    with db.conectar() as conn:
        mortas = [r[0] for r in conn.execute("SELECT id FROM tarefa_morta")]
    no_erp_antes = len(falsos.estado["pedidos_erp"])
    # Nenhum pedido some: ou entrou, ou está na fila de mortos (com alerta) esperando reprocessar.
    assert no_erp_antes + len(mortas) == n
    for m in mortas:  # operador clica "reprocessar" no /admin
        fila.reprocessar(m)
    rodar_ate_esvaziar()
    with db.conectar() as conn:
        vinculos = conn.execute("SELECT count(*) FROM vinculo_pedido").fetchone()[0]
    resultado = {"pedidos": n, "falha_injetada": "20%", "na_primeira_passada": no_erp_antes,
                 "mortas_reprocessadas": len(mortas), "no_erp": len(falsos.estado["pedidos_erp"]),
                 "vinculos": vinculos, "duplicados": falsos.estado["duplicados"], "perdidos": n - vinculos}
    print("CARGA", json.dumps(resultado))
    assert (resultado["no_erp"], vinculos, resultado["duplicados"]) == (n, n, 0)
