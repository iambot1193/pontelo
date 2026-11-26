"""Bling API v3. Campos conferidos na especificação OpenAPI oficial (docs/bling-api.md)."""
import os
from datetime import date

from app.http import chamar

CONTATO_ID = int(os.environ.get("BLING_CONTATO_ID", "1"))  # ponytail: contato fixo "Mercado Livre"
# Spec marca "parcelas" como obrigatório no POST; exige forma de pagamento cadastrada no Bling.
FORMA_PAGAMENTO_ID = os.environ.get("BLING_FORMA_PAGAMENTO_ID", "")
LOJA_ID = os.environ.get("BLING_LOJA_ID", "")  # opcional: canal de venda "Mercado Livre" no Bling


def criar_pedido(numero_loja: str, itens: list[dict], data: str | None = None) -> str:
    """Idempotente por numeroLoja: se já existe (resposta perdida num POST anterior), devolve o existente."""
    achados = chamar("bling", "GET", "/pedidos/vendas", params={"numerosLojas[]": numero_loja})
    if achados.get("data"):
        return str(achados["data"][0]["id"])
    dia = data or date.today().isoformat()
    corpo = {
        "numeroLoja": numero_loja,
        "data": dia, "dataSaida": dia, "dataPrevista": dia,
        "contato": {"id": CONTATO_ID},
        "itens": [{"codigo": i.get("sku", ""),
                   "descricao": i.get("descricao") or i.get("sku", "Item Mercado Livre"),
                   "quantidade": i["quantidade"], "valor": i["valor"]}
                  | ({"produto": {"id": int(i["produto_erp"])}} if i.get("produto_erp") else {})  # sem = item avulso
                  for i in itens],
    }
    if FORMA_PAGAMENTO_ID:
        total = round(sum(i["quantidade"] * i["valor"] for i in itens), 2)
        corpo["parcelas"] = [{"dataVencimento": dia, "valor": total,
                              "formaPagamento": {"id": int(FORMA_PAGAMENTO_ID)}}]
    if LOJA_ID:
        corpo["loja"] = {"id": int(LOJA_ID)}
    return str(chamar("bling", "POST", "/pedidos/vendas", json=corpo)["data"]["id"])


def buscar_estoque(produtos: list[str]) -> dict[str, int]:
    """Saldo virtual (desconta reservas). O Bling filtra por padrão só saldo positivo
    (filtroSaldoEstoque=1), então produto ausente na resposta = zerado ou negativo -> 0."""
    r = chamar("bling", "GET", "/estoques/saldos", params={"idsProdutos[]": produtos})
    saldos = {str(s["produto"]["id"]): max(0, int(s["saldoVirtualTotal"])) for s in r["data"]}
    return {p: saldos.get(str(p), 0) for p in produtos}
