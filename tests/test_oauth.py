import threading

from fastapi.testclient import TestClient

from app import db, oauth
from app.main import app
from tests.falsos import app as falsos


def conectar(prov="ml"):
    c = TestClient(app, follow_redirects=False)
    state = c.get(f"/conectar/{prov}").headers["location"].split("state=")[1]
    r = c.get(f"/callback/{prov}", params={"code": f"codigo-{prov}", "state": state})
    assert r.json() == {"conectado": prov}


def vencer(prov="ml"):
    with db.conectar() as conn:
        conn.execute("UPDATE credencial SET expira_em = now() WHERE provedor = %s", (prov,))


def test_conecta_e_cifra():
    conectar()
    tok = oauth.token("ml")
    with db.conectar() as conn:
        bruto = conn.execute("SELECT access_token FROM credencial").fetchone()[0]
    assert tok.encode() not in bytes(bruto)
    assert falsos.estado["renovacoes"]["ml"] == 0


def test_state_invalido():
    assert TestClient(app).get("/callback/ml", params={"code": "x", "state": "y"}).status_code == 400


def test_renova_perto_de_vencer():
    conectar("bling")
    antigo = oauth.token("bling")
    vencer("bling")
    assert oauth.token("bling") != antigo
    assert falsos.estado["renovacoes"]["bling"] == 1


def test_concorrencia_renova_uma_vez():
    conectar()
    vencer()
    erros = []

    def pegar():
        try:
            oauth.token("ml")
        except Exception as e:
            erros.append(e)

    ts = [threading.Thread(target=pegar) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not erros
    assert falsos.estado["renovacoes"]["ml"] == 1


def test_401_nao_renova_duas_vezes():
    conectar()
    usado = oauth.token("ml")
    novo = oauth.token_apos_401("ml", usado)
    assert oauth.token_apos_401("ml", usado) == novo  # segundo worker reaproveita
    assert falsos.estado["renovacoes"]["ml"] == 1
