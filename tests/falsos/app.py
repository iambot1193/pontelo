"""APIs falsas de Mercado Livre e Bling (só rotas usadas). Dados inventados.

Modo falhar: POST /_falhar {"ml": [500, 429], "bling": [500]} faz as próximas
chamadas do provedor devolverem esses status, em ordem.
"""
import random
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI(title="falsos")
estado: dict = {}


def resetar(expira_em: int = 21600):
    estado.clear()
    estado.update(
        falhas={"ml": [], "bling": []},
        taxa_falha=0.0,                      # fração de chamadas que falham ao acaso
        posts_pedido=0,
        duplicados=0,                        # POST de pedido que já existia
        tokens={"ml": {}, "bling": {}},     # access -> expira (epoch)
        refresh={"ml": set(), "bling": set()},
        expira_em=expira_em,
        renovacoes={"ml": 0, "bling": 0},
        pedidos_ml={},                       # id -> ordem
        pedidos_erp={},                    # numeroLoja -> pedido
        estoque_ml={},                       # item_id -> qtd
        estoque_erp={},                      # produto_id -> qtd
    )


resetar()


@app.post("/_falhar")
async def falhar(req: Request):
    for prov, codigos in (await req.json()).items():
        estado["falhas"][prov].extend(codigos)
    return {"ok": True}


@app.post("/_resetar")
def _resetar(expira_em: int = 21600):
    resetar(expira_em)
    return {"ok": True}


def criar_router(prov: str) -> APIRouter:
    r = APIRouter(prefix=f"/{prov}")

    @r.get("/authorize")
    def authorize(redirect_uri: str, state: str = ""):
        q = urlencode({"code": f"codigo-{prov}", "state": state})
        return RedirectResponse(f"{redirect_uri}?{q}")

    @r.post("/oauth/token")
    def token(grant_type: str = Form(...), code: str = Form(""), refresh_token: str = Form("")):
        if grant_type == "authorization_code" and code != f"codigo-{prov}":
            return JSONResponse({"error": "invalid_grant"}, 400)
        if grant_type == "refresh_token":
            if refresh_token not in estado["refresh"][prov]:
                return JSONResponse({"error": "invalid_grant"}, 400)
            estado["refresh"][prov].discard(refresh_token)  # uso único, como o ML
            estado["renovacoes"][prov] += 1
        access, novo = secrets.token_hex(8), secrets.token_hex(8)
        estado["tokens"][prov][access] = time.time() + estado["expira_em"]
        estado["refresh"][prov].add(novo)
        return {"access_token": access, "refresh_token": novo,
                "expires_in": estado["expira_em"], "token_type": "Bearer", "user_id": 999}

    return r


app.include_router(criar_router("ml"))
app.include_router(criar_router("bling"))


@app.middleware("http")
async def checar(req: Request, call_next):
    prov = req.url.path.strip("/").split("/")[0]
    if prov not in ("ml", "bling") or req.url.path.endswith("/authorize"):
        return await call_next(req)
    sorteio = estado["taxa_falha"] and random.random() < estado["taxa_falha"]
    if estado["falhas"][prov] or sorteio:
        codigo = estado["falhas"][prov].pop(0) if estado["falhas"][prov] else random.choice([500, 503, 429])
        headers = {"Retry-After": "1"} if codigo == 429 else {}
        return JSONResponse({"error": "falha injetada"}, codigo, headers=headers)
    if not req.url.path.endswith("/oauth/token"):
        access = req.headers.get("authorization", "").removeprefix("Bearer ")
        if estado["tokens"][prov].get(access, 0) < time.time():
            return JSONResponse({"error": "invalid_token"}, 401)
    return await call_next(req)


@app.get("/ml/users/me")
def ml_me():
    return {"id": 999, "nickname": "TESTE_VENDEDOR"}


@app.get("/ml/orders/search")
def ml_buscar(offset: int = 0, limit: int = 50):
    todos = sorted(estado["pedidos_ml"].values(), key=lambda p: p["id"])
    return {"results": todos[offset:offset + limit],
            "paging": {"total": len(todos), "offset": offset, "limit": limit}}


@app.get("/ml/orders/{id}")
def ml_pedido(id: str):
    if id not in estado["pedidos_ml"]:
        return JSONResponse({"error": "not_found"}, 404)
    return estado["pedidos_ml"][id]


@app.get("/bling/pedidos/vendas")
def bling_listar(req: Request):
    numeros = req.query_params.getlist("numerosLojas[]")
    return {"data": [p for n, p in estado["pedidos_erp"].items() if n in numeros]}


@app.post("/bling/pedidos/vendas")
async def bling_criar(req: Request):
    corpo = await req.json()
    estado["posts_pedido"] += 1
    if corpo["numeroLoja"] in estado["pedidos_erp"]:
        estado["duplicados"] += 1
        return JSONResponse({"error": "duplicado"}, 400)
    faltando = [c for c in ("contato", "data", "dataPrevista", "itens") if not corpo.get(c)]
    faltando += [f"itens.{c}" for i in corpo.get("itens", []) for c in ("descricao", "quantidade", "valor")
                 if c not in i]
    if faltando:
        return JSONResponse({"error": {"type": "VALIDATION_ERROR", "fields": faltando}}, 400)
    pedido = {"id": 5000 + len(estado["pedidos_erp"]), **corpo}
    estado["pedidos_erp"][corpo["numeroLoja"]] = pedido
    return JSONResponse({"data": {"id": pedido["id"]}}, 201)  # spec: 201


@app.put("/ml/items/{id}")
async def ml_item(id: str, req: Request):
    estado["estoque_ml"][id] = (await req.json())["available_quantity"]
    return {"id": id, "available_quantity": estado["estoque_ml"][id]}


@app.get("/bling/estoques/saldos")
def bling_saldos(req: Request):
    ids = req.query_params.getlist("idsProdutos[]")
    return {"data": [{"produto": {"id": int(i)}, "saldoFisicoTotal": q, "saldoVirtualTotal": q}
                     for i, q in estado["estoque_erp"].items()
                     if i in ids and q > 0]}  # como o real: filtroSaldoEstoque=1 (só positivo) por padrão


@app.post("/_demo/pedido/{id}")
def demo_pedido(id: str, sku: str = "SKU-1"):
    """Para a demo sem conta: cria um pedido no ML falso (depois mande o webhook)."""
    return pedido_ml_exemplo(id, sku)


@app.post("/_demo/estoque/{produto}")
def demo_estoque(produto: str, qtd: int):
    estado["estoque_erp"][produto] = qtd
    return {"produto": produto, "qtd": qtd}


@app.get("/_demo/estado")
def demo_estado():
    return {"pedidos_erp": estado["pedidos_erp"], "estoque_ml": estado["estoque_ml"],
            "renovacoes": estado["renovacoes"]}


def pedido_ml_exemplo(id: str, sku: str = "SKU-1") -> dict:
    """Formato de /orders/{id} da doc do ML, dados inventados."""
    p = {"id": int(id), "status": "paid", "date_created": "2026-11-23T10:00:00.000-03:00",
         "order_items": [{"item": {"id": "MLB100", "seller_sku": sku, "title": "Caneca teste"},
                          "quantity": 2, "unit_price": 49.9}]}
    estado["pedidos_ml"][id] = p
    return p
