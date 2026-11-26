from app import db
from app.erp import erp
from app.http import ErroPermanente, chamar


def importar(pedido_ml: str):
    with db.conectar() as conn:
        if conn.execute("SELECT 1 FROM vinculo_pedido WHERE pedido_ml = %s", (pedido_ml,)).fetchone():
            return
        ordem = chamar("ml", "GET", f"/orders/{pedido_ml}")
        itens, faltando = [], []
        for oi in ordem["order_items"]:
            sku = oi["item"].get("seller_sku") or oi["item"]["id"]
            linha = conn.execute("SELECT produto_erp FROM mapa_sku WHERE sku_ml = %s", (sku,)).fetchone()
            if not linha:
                faltando.append(sku)
                continue
            itens.append({"produto_erp": linha[0], "sku": sku, "descricao": oi["item"].get("title"),
                          "quantidade": oi["quantity"], "valor": oi["unit_price"]})
        if faltando:
            # ponytail: "pendente de mapeamento" = fila de mortos + alerta; cadastrar SKU e reprocessar
            raise ErroPermanente(f"pedido {pedido_ml}: SKU sem mapeamento {faltando}")
        pedido_erp = erp.criar_pedido(pedido_ml, itens, (ordem.get("date_created") or "")[:10] or None)
        conn.execute("INSERT INTO vinculo_pedido (pedido_ml, pedido_erp) VALUES (%s, %s)"
                     " ON CONFLICT DO NOTHING", (pedido_ml, pedido_erp))
