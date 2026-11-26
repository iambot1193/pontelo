"""Estoque ERP -> ML. ERP é a fonte da verdade.

ponytail: polling de todos os SKUs mapeados a cada 5 min (lote de 100). Webhook do ERP
quando o catálogo passar de alguns milhares de SKUs.
"""
from app import db, fila
from app.erp import erp
from app.http import chamar

ENVIADO = "pontelo:estoque_enviado"  # sku -> última quantidade enviada ao ML


def verificar(_=""):
    with db.conectar() as conn:
        mapa = conn.execute("SELECT sku_ml, produto_erp FROM mapa_sku").fetchall()
    for i in range(0, len(mapa), 100):
        lote = mapa[i:i + 100]
        saldos = erp.buscar_estoque([p for _, p in lote])
        for sku, prod in lote:
            if prod in saldos and fila.r.hget(ENVIADO, sku) != str(saldos[prod]):
                fila.enfileirar(f"estoque:{sku}")


def sincronizar(sku: str):
    with db.conectar() as conn:
        linha = conn.execute("SELECT item_ml, produto_erp FROM mapa_sku WHERE sku_ml = %s", (sku,)).fetchone()
    if not linha:
        return
    item, prod = linha
    qtd = erp.buscar_estoque([prod])[prod]  # lê na hora: só o último valor importa
    chamar("ml", "PUT", f"/items/{item}", json={"available_quantity": qtd})
    fila.r.hset(ENVIADO, sku, str(qtd))
