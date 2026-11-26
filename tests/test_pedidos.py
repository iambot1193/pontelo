import time

from fastapi.testclient import TestClient

from app import db, fila
from app.main import app
from app.worker import HANDLERS
from tests.falsos import app as falsos

api = TestClient(app)
FUTURO = time.time() + 10**7  # libera toda retentativa agendada


def aviso(id_ml="123", sent="2026-11-23T10:00:00Z"):
    return {"topic": "orders_v2", "resource": f"/orders/{id_ml}", "user_id": 999,
            "application_id": "teste", "sent": sent}


def rodar_ate_esvaziar():
    while fila.processar_pendentes(HANDLERS, agora=FUTURO):
        pass


def mortas():
    with db.conectar() as conn:
        return conn.execute("SELECT tarefa, erro FROM tarefa_morta").fetchall()


def test_webhook_5_vezes_1_pedido(conectado):
    falsos.pedido_ml_exemplo("123")
    for _ in range(5):
        assert api.post("/webhooks/ml", json=aviso()).status_code == 200
    rodar_ate_esvaziar()
    assert len(falsos.estado["pedidos_erp"]) == 1
    assert falsos.estado["pedidos_erp"]["123"]["itens"][0]["produto"]["id"] == 777


def test_aviso_de_outra_aplicacao_ignorado(conectado):
    assert api.post("/webhooks/ml", json={**aviso(), "application_id": "intruso"}).json() == {"ignorado": "application_id"}
    assert fila.r.llen(fila.FILA) == 0


def test_erp_500_tres_vezes_entra_uma_vez(conectado):
    falsos.pedido_ml_exemplo("123")
    falsos.estado["falhas"]["bling"] = [500, 500, 500]
    api.post("/webhooks/ml", json=aviso())
    rodar_ate_esvaziar()
    assert list(falsos.estado["pedidos_erp"]) == ["123"]
    assert not mortas()


def test_resposta_perdida_nao_duplica(conectado):
    """POST criou no ERP mas o worker caiu antes de gravar o vínculo: reprocessar não duplica."""
    falsos.pedido_ml_exemplo("123")
    falsos.estado["pedidos_erp"]["123"] = {"id": 4242, "numeroLoja": "123"}
    fila.enfileirar("importar_pedido:123")
    rodar_ate_esvaziar()
    with db.conectar() as conn:
        assert conn.execute("SELECT pedido_erp FROM vinculo_pedido").fetchone()[0] == "4242"
    assert len(falsos.estado["pedidos_erp"]) == 1


def test_429_espera_e_segue(conectado):
    falsos.pedido_ml_exemplo("123")
    falsos.estado["falhas"]["ml"] = [429, 429]
    fila.enfileirar("importar_pedido:123")
    fila.processar_pendentes(HANDLERS)  # uma rodada só: 429 não vira retentativa da fila
    assert "123" in falsos.estado["pedidos_erp"]


def test_token_vencido_no_meio_renova_uma_vez(conectado):
    for i in range(1, 6):
        falsos.pedido_ml_exemplo(str(i))
        fila.enfileirar(f"importar_pedido:{i}")
    falsos.estado["tokens"]["ml"].clear()  # todo access token do ML inválido
    rodar_ate_esvaziar()
    assert len(falsos.estado["pedidos_erp"]) == 5
    assert falsos.estado["renovacoes"]["ml"] == 1


def test_sku_sem_mapa_vai_para_mortos_sem_repetir(conectado):
    falsos.pedido_ml_exemplo("123", sku="SKU-NOVO")
    fila.enfileirar("importar_pedido:123")
    rodar_ate_esvaziar()
    [(tarefa, erro)] = mortas()
    assert tarefa == "importar_pedido:123" and "SKU-NOVO" in erro


def test_500_sempre_morre_depois_das_retentativas(conectado):
    falsos.pedido_ml_exemplo("123")
    falsos.estado["falhas"]["bling"] = [500] * 20
    fila.enfileirar("importar_pedido:123")
    rodar_ate_esvaziar()
    assert len(mortas()) == 1
    assert not falsos.estado["pedidos_erp"]
