import logging
import os

import httpx

log = logging.getLogger("alerta")


def enviar(texto: str):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    log.error(texto)
    if not (token and chat):
        return
    try:
        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat, "text": f"[pontelo] {texto}"}, timeout=10)
    except httpx.HTTPError:
        log.exception("telegram falhou")  # alerta nunca derruba o worker
