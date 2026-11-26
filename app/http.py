"""Chamada autenticada a provedor: renova em 401 (uma vez), espera Retry-After em 429."""
import time

import httpx

from app import config


class ErroPermanente(Exception):
    """Erro de dado (4xx): repetir não resolve, vai direto para mortos."""


class ErroTemporario(Exception):
    """5xx/429 esgotado/rede: a fila tenta de novo."""


def cliente() -> httpx.Client:
    # ponytail: ponto único de criação; testes trocam por TestClient das APIs falsas.
    return httpx.Client(timeout=10)


def chamar(prov: str, metodo: str, caminho: str, **kw) -> dict:
    from app import oauth  # import tardio: oauth usa cliente() daqui

    tok = oauth.token(prov)
    renovou = False
    for _ in range(4):
        with cliente() as c:
            r = c.request(metodo, config.PROVEDORES[prov]["api"] + caminho,
                          headers={"Authorization": f"Bearer {tok}"}, **kw)
        if r.status_code == 401 and not renovou:
            tok, renovou = oauth.token_apos_401(prov, tok), True
            continue
        if r.status_code == 429:
            # ponytail: espera no próprio worker; limitador por provedor no Redis se tiver vários workers
            time.sleep(min(float(r.headers.get("Retry-After", 2)), 60))
            continue
        if r.status_code >= 500:
            raise ErroTemporario(f"{prov} {metodo} {caminho}: {r.status_code}")
        if r.status_code >= 400:
            raise ErroPermanente(f"{prov} {metodo} {caminho}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}
    raise ErroTemporario(f"{prov} {metodo} {caminho}: tentativas esgotadas ({r.status_code})")
