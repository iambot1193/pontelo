"""Confere pedidos do ML das últimas 48 h com os vínculos. Pega o que o webhook perdeu."""
from datetime import UTC, datetime, timedelta

from app import alerta, db, fila
from app.http import chamar


def conciliar(_=""):
    vendedor = chamar("ml", "GET", "/users/me")["id"]
    desde = (datetime.now(UTC) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
    ids, offset = [], 0
    while True:
        pag = chamar("ml", "GET", "/orders/search", params={
            "seller": vendedor, "order.date_created.from": desde, "offset": offset, "limit": 50})
        ids += [str(o["id"]) for o in pag["results"]]
        offset += 50
        if offset >= pag["paging"]["total"]:
            break
    with db.conectar() as conn:
        feitos = {r[0] for r in conn.execute(
            "SELECT pedido_ml FROM vinculo_pedido WHERE pedido_ml = ANY(%s)", (ids,))}
        conn.execute("DELETE FROM evento_webhook WHERE recebido_em < now() - interval '30 days'")  # LGPD
    faltando = [i for i in ids if i not in feitos]
    for i in faltando:
        fila.enfileirar(f"importar_pedido:{i}")
    if faltando:
        alerta.enviar(f"conciliação achou {len(faltando)} pedido(s) sem vínculo: {faltando[:10]}")
    return faltando
