import json

from fastapi import APIRouter, Request

from app import config, db, fila, oauth

router = APIRouter()


@router.post("/webhooks/ml")
async def ml(req: Request):
    aviso = await req.json()
    if str(aviso.get("application_id")) != config.PROVEDORES["ml"]["client_id"]:
        return {"ignorado": "application_id"}  # 200 para o ML não insistir
    conta = fila.r.get(oauth.ML_USER_ID)
    if conta and str(aviso.get("user_id")) != conta:
        return {"ignorado": "user_id"}
    # _id é único por aviso; reenvio do mesmo aviso repete o _id. Sem _id: topic+resource+sent.
    id_evento = aviso.get("_id") or f"{aviso['topic']}:{aviso['resource']}:{aviso.get('sent', '')}"
    with db.conectar() as conn:
        novo = conn.execute(
            "INSERT INTO evento_webhook (id, payload) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (id_evento, json.dumps(aviso))).fetchone()
    if novo and aviso["topic"] == "orders_v2":
        # mesmo pedido avisado de novo (mudança de status) é barrado pelo vínculo em pedidos.importar
        fila.enfileirar(f"importar_pedido:{aviso['resource'].rsplit('/', 1)[-1]}")
    return {"ok": True}
