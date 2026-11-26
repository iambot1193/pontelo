"""Checagem só de leitura das contas conectadas. Uso: docker compose exec api python -m scripts.verificar"""
from app import db, oauth
from app.erp import bling
from app.http import chamar


def t(nome, f):
    try:
        print(f"  OK    {nome}: {f()}")
    except Exception as e:
        print(f"  FALHA {nome}: {str(e)[:120]}")


with db.conectar() as conn:
    print("Credenciais:", conn.execute("SELECT provedor, expira_em FROM credencial").fetchall() or "nenhuma")

if oauth.conectado("bling"):
    print("Bling:")
    t("forma de pagamento", lambda: chamar("bling", "GET", f"/formas-pagamentos/{bling.FORMA_PAGAMENTO_ID}")["data"]["descricao"])
    t("pedidos de venda (leitura)",
      lambda: f"{len(chamar('bling', 'GET', '/pedidos/vendas', params={'limite': 1})['data'])} retornado(s)")
    t("saldos de estoque", lambda: chamar("bling", "GET", "/estoques/saldos", params={"idsProdutos[]": ["1"]}) and "acesso ok")
if oauth.conectado("ml"):
    print("Mercado Livre:")
    eu = chamar("ml", "GET", "/users/me")
    print(f"  OK    usuário: {eu['id']} {eu['nickname']}")
    t("pedidos (busca)", lambda: chamar("ml", "GET", "/orders/search", params={"seller": eu["id"], "limit": 1})["paging"])
