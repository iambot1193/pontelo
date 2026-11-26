import html
import os
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app import db, fila

basic = HTTPBasic()


def autenticar(c: HTTPBasicCredentials = Depends(basic)):
    senha = os.environ.get("ADMIN_SENHA", "")
    if not senha or not secrets.compare_digest(c.password.encode(), senha.encode()):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


router = APIRouter(prefix="/admin", dependencies=[Depends(autenticar)])


@router.get("", response_class=HTMLResponse)
def painel():
    with db.conectar() as conn:
        hoje = conn.execute("SELECT count(*) FROM vinculo_pedido WHERE criado_em >= current_date").fetchone()[0]
        ultimo = conn.execute("SELECT max(criado_em) FROM vinculo_pedido").fetchone()[0]
        creds = conn.execute("SELECT provedor, conta, expira_em FROM credencial ORDER BY 1").fetchall()
        skus = conn.execute("SELECT sku_ml, item_ml, produto_erp FROM mapa_sku ORDER BY 1").fetchall()
        mortas = conn.execute("SELECT id, tarefa, erro, tentativas, morta_em FROM tarefa_morta"
                              " ORDER BY id DESC LIMIT 100").fetchall()
    e = lambda v: html.escape(str(v))
    linhas_mortas = "".join(
        f"<tr><td>{e(m[1])}</td><td>{e(m[2])[:200]}</td><td>{m[3]}</td><td>{e(m[4])}</td>"
        f"<td><form method=post action='/admin/mortos/{m[0]}/reprocessar'><button>reprocessar</button></form></td></tr>"
        for m in mortas)
    linhas_skus = "".join(f"<tr><td>{e(s)}</td><td>{e(i)}</td><td>{e(p)}</td></tr>" for s, i, p in skus)
    linhas_creds = "".join(f"<li>{e(p)}/{e(c)}: expira {e(x)}</li>" for p, c, x in creds)
    return f"""<!doctype html><meta charset=utf-8><title>pontelo</title>
<style>body{{font-family:sans-serif;margin:2em}}td{{border-bottom:1px solid #ccc;padding:4px}}</style>
<h1>pontelo</h1>
<p>Pedidos hoje: <b>{hoje}</b> · último: {e(ultimo)} · fila: {fila.r.llen(fila.FILA)}
· agendadas: {fila.r.zcard(fila.AGENDADAS)} · mortas: {len(mortas)}</p>
<h2>Tokens</h2><ul>{linhas_creds or '<li>nenhum: <a href=/conectar/ml>ML</a> · <a href=/conectar/bling>Bling</a></li>'}</ul>
<h2>Mapa de SKU</h2><table><tr><th>SKU ML</th><th>anúncio ML</th><th>produto ERP</th></tr>{linhas_skus}</table>
<form method=post action=/admin/sku><input name=sku_ml placeholder="SKU-1" required>
<input name=item_ml placeholder="MLB123" required><input name=produto_erp placeholder="id no ERP" required>
<button>salvar</button></form>
<h2>Fila de mortos</h2><table>{linhas_mortas or '<tr><td>vazia</td></tr>'}</table>"""


@router.post("/sku")
def cadastrar_sku(sku_ml: str = Form(...), item_ml: str = Form(...), produto_erp: str = Form(...)):
    with db.conectar() as conn:
        conn.execute("INSERT INTO mapa_sku VALUES (%s, %s, %s) ON CONFLICT (sku_ml) DO UPDATE"
                     " SET item_ml = EXCLUDED.item_ml, produto_erp = EXCLUDED.produto_erp",
                     (sku_ml.strip(), item_ml.strip(), produto_erp.strip()))
    return RedirectResponse("/admin", 303)


@router.post("/mortos/{id}/reprocessar")
def reprocessar(id: int):
    fila.reprocessar(id)
    return RedirectResponse("/admin", 303)
