import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
FERNET_KEY = os.environ["FERNET_KEY"]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
FALSOS = os.environ.get("FALSOS_URL", "http://localhost:9000")
# Tela de autorização abre no navegador do usuário, que não resolve o nome interno "falsos".
FALSOS_PUBLICO = os.environ.get("FALSOS_PUBLICO_URL", FALSOS)


def _prov(nome: str) -> dict:
    # Padrão aponta para as APIs falsas. Contas reais: definir no .env (fase 4).
    env = lambda k, d: os.environ.get(f"{nome.upper()}_{k}", d)
    return {
        "auth_url": env("AUTH_URL", f"{FALSOS_PUBLICO}/{nome}/authorize"),
        "token_url": env("TOKEN_URL", f"{FALSOS}/{nome}/oauth/token"),
        "api": env("API", f"{FALSOS}/{nome}"),
        "client_id": env("CLIENT_ID", "teste"),
        "client_secret": env("CLIENT_SECRET", "teste"),
    }


PROVEDORES = {"ml": _prov("ml"), "bling": _prov("bling")}
