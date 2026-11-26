"""OAuth 2.0 authorization code + renovação com trava por linha (refresh do ML é de uso único)."""
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app import config, db, fila, http

router = APIRouter()
fernet = Fernet(config.FERNET_KEY)
MARGEM = timedelta(minutes=10)
ML_USER_ID = "pontelo:ml_user_id"  # conta ML conectada; webhook de outra conta é ignorado


def _redirect(prov: str) -> str:
    return f"{config.BASE_URL}/callback/{prov}"


def _pedir_token(prov: str, dados: dict) -> dict:
    p = config.PROVEDORES[prov]
    with http.cliente() as c:
        r = c.post(p["token_url"],
                   data={**dados, "client_id": p["client_id"], "client_secret": p["client_secret"]},
                   auth=(p["client_id"], p["client_secret"]))  # Bling exige Basic
    if r.status_code != 200:
        raise RuntimeError(f"token {prov}: {r.status_code} {r.text[:200]}")
    return r.json()


def _salvar(conn, prov: str, conta: str, tok: dict):
    expira = datetime.now(UTC) + timedelta(seconds=tok["expires_in"])
    conn.execute(
        """INSERT INTO credencial (provedor, conta, access_token, refresh_token, expira_em)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (provedor, conta) DO UPDATE SET access_token = EXCLUDED.access_token,
             refresh_token = EXCLUDED.refresh_token, expira_em = EXCLUDED.expira_em""",
        (prov, conta, fernet.encrypt(tok["access_token"].encode()),
         fernet.encrypt(tok["refresh_token"].encode()), expira))


def token(prov: str, conta: str = "principal", forcar: bool = False) -> str:
    """Access token válido. Renova se faltar < 10 min ou forcar=True."""
    with db.conectar() as conn, conn.transaction():
        linha = conn.execute(
            "SELECT access_token, refresh_token, expira_em FROM credencial"
            " WHERE provedor = %s AND conta = %s FOR UPDATE", (prov, conta)).fetchone()
        if not linha:
            raise RuntimeError(f"{prov}/{conta} não conectado: abrir /conectar/{prov}")
        access, refresh, expira = linha
        if not forcar and expira - datetime.now(UTC) > MARGEM:
            return fernet.decrypt(access).decode()
        tok = _pedir_token(prov, {"grant_type": "refresh_token",
                                  "refresh_token": fernet.decrypt(refresh).decode()})
        _salvar(conn, prov, conta, tok)
        return tok["access_token"]


def conectado(*provs: str) -> bool:
    with db.conectar() as conn:
        n = conn.execute("SELECT count(DISTINCT provedor) FROM credencial WHERE provedor = ANY(%s)",
                         (list(provs),)).fetchone()[0]
    return n == len(provs)


def token_apos_401(prov: str, usado: str, conta: str = "principal") -> str:
    """Outro worker pode já ter renovado: só força se o token no banco ainda é o usado."""
    atual = token(prov, conta)
    return token(prov, conta, forcar=True) if atual == usado else atual


@router.get("/conectar/{prov}")
def conectar(prov: str):
    if prov not in config.PROVEDORES:
        raise HTTPException(404)
    state = secrets.token_urlsafe(16)
    fila.r.set(f"pontelo:oauth_state:{state}", prov, ex=600)
    p = config.PROVEDORES[prov]
    q = urlencode({"response_type": "code", "client_id": p["client_id"],
                   "redirect_uri": _redirect(prov), "state": state})
    return RedirectResponse(f"{p['auth_url']}?{q}")


@router.get("/callback/{prov}")
def callback(prov: str, code: str, state: str):
    if fila.r.getdel(f"pontelo:oauth_state:{state}") != prov:  # uso único, expira em 10 min
        raise HTTPException(400, "state inválido")
    tok = _pedir_token(prov, {"grant_type": "authorization_code", "code": code,
                              "redirect_uri": _redirect(prov)})
    with db.conectar() as conn:
        _salvar(conn, prov, "principal", tok)
    if prov == "ml" and tok.get("user_id"):
        fila.r.set(ML_USER_ID, str(tok["user_id"]))
    return {"conectado": prov}
