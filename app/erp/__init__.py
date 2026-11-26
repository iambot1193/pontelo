"""Contrato do ERP (um módulo por ERP, mesmas funções):
  criar_pedido(numero_loja, itens) -> id   idempotente por numero_loja
  buscar_estoque([produto_erp]) -> {produto_erp: qtd}
Trocar Bling por Tiny = tiny.py com as mesmas duas funções + ERP=tiny no .env."""
import os

from app.erp import bling

ERPS = {"bling": bling}
erp = ERPS[os.environ.get("ERP", "bling")]
