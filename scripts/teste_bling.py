"""Cria um pedido de TESTE real no Bling, confere a idempotência e apaga.
Uso: docker compose exec api python -m scripts.teste_bling [id_produto_bling] [--manter]
Sem id de produto: item avulso (só descrição)."""
import sys
import time

from app.erp import bling
from app.http import chamar

produto = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
numero = f"TESTE-PONTELO-{int(time.time())}"
item = [{"produto_erp": produto, "sku": "TESTE", "descricao": "Teste pontelo (pode apagar)",
         "quantidade": 1, "valor": 1.0}]
id1 = bling.criar_pedido(numero, item)
print("criado:", numero, "id", id1)
id2 = bling.criar_pedido(numero, item)
print("2a chamada (idempotência):", "OK mesmo id" if id1 == id2 else f"DUPLICOU id {id2}")
p = chamar("bling", "GET", f"/pedidos/vendas/{id1}")["data"]
print("no Bling:", p.get("numero"), p.get("numeroLoja"), "total", p.get("total"))
if "--manter" not in sys.argv:
    for i in {id1, id2}:
        try:
            chamar("bling", "DELETE", f"/pedidos/vendas/{i}")
            print("apagado:", i)
        except Exception as e:  # app não precisa do escopo de excluir; apagar à mão
            print(f"não apagou {i} ({str(e)[:60]}): apague {numero} em Vendas → Pedidos de venda")
