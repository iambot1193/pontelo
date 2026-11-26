import threading

from fastapi.testclient import TestClient

from app import conciliar, db, estoque, fila
from app.main import app
from tests.falsos import app as falsos
from tests.test_pedidos import rodar_ate_esvaziar


def test_estoque_erp_vai_para_ml_e_nao_repete(conectado):
    falsos.estado["estoque_erp"]["777"] = 8
    estoque.verificar()
    rodar_ate_esvaziar()
    assert falsos.estado["estoque_ml"] == {"MLB100": 8}
    estoque.verificar()  # sem mudança: nada novo na fila
    assert fila.r.llen(fila.FILA) == 0
    falsos.estado["estoque_erp"]["777"] = 3
    estoque.verificar()
    rodar_ate_esvaziar()
    assert falsos.estado["estoque_ml"] == {"MLB100": 3}
    falsos.estado["estoque_erp"]["777"] = 0  # Bling some com o produto da resposta
    estoque.verificar()
    rodar_ate_esvaziar()
    assert falsos.estado["estoque_ml"] == {"MLB100": 0}


def test_pedido_no_bling_tem_campos_da_spec(conectado):
    falsos.pedido_ml_exemplo("321")
    fila.enfileirar("importar_pedido:321")
    rodar_ate_esvaziar()
    p = falsos.estado["pedidos_erp"]["321"]
    assert p["data"] == "2026-11-23" and p["itens"][0]["descricao"] == "Caneca teste"
    assert p["itens"][0]["codigo"] == "SKU-1"


def test_conciliacao_pega_webhook_perdido(conectado):
    for i in range(1, 61):  # 2 páginas
        falsos.pedido_ml_exemplo(str(i))
    fila.enfileirar("importar_pedido:1")
    rodar_ate_esvaziar()
    assert len(conciliar.conciliar()) == 59
    rodar_ate_esvaziar()
    assert len(falsos.estado["pedidos_erp"]) == 60
    assert conciliar.conciliar() == []


def test_dois_workers_50_pedidos_sem_duplicata(conectado):
    for i in range(1, 51):
        falsos.pedido_ml_exemplo(str(i))
        fila.enfileirar(f"importar_pedido:{i}")
        fila.enfileirar(f"importar_pedido:{i}")  # webhook + conciliação ao mesmo tempo
    with db.conectar() as conn:
        conn.execute("UPDATE credencial SET expira_em = now()")
    ts = [threading.Thread(target=rodar_ate_esvaziar) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(falsos.estado["pedidos_erp"]) == 50
    assert falsos.estado["renovacoes"] == {"ml": 1, "bling": 1}


def test_admin_exige_senha_e_reprocessa(conectado, monkeypatch):
    monkeypatch.setenv("ADMIN_SENHA", "s3gredo")
    c = TestClient(app)
    assert c.get("/admin").status_code == 401
    assert c.get("/admin", auth=("x", "errada")).status_code == 401
    falsos.pedido_ml_exemplo("9", sku="SEM-MAPA")
    fila.enfileirar("importar_pedido:9")
    rodar_ate_esvaziar()
    assert "importar_pedido:9" in c.get("/admin", auth=("x", "s3gredo")).text
    with db.conectar() as conn:
        id_morta = conn.execute("SELECT id FROM tarefa_morta").fetchone()[0]
        conn.execute("INSERT INTO mapa_sku VALUES ('SEM-MAPA', 'MLB9', '778')")
    c.post(f"/admin/mortos/{id_morta}/reprocessar", auth=("x", "s3gredo"))
    rodar_ate_esvaziar()
    assert "9" in falsos.estado["pedidos_erp"]
