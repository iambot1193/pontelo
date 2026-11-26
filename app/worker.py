import logging
import time

from app import conciliar, estoque, fila, oauth, pedidos

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("worker")
logging.getLogger("httpx").setLevel(logging.WARNING)
HANDLERS = {
    "importar_pedido": pedidos.importar,
    "estoque": estoque.sincronizar,
    "verificar_estoque": estoque.verificar,
    "conciliar": conciliar.conciliar,
}
PERIODICAS = {"verificar_estoque": 300, "conciliar": 3600}

if __name__ == "__main__":
    log.info(f"worker no ar; recuperadas {fila.recuperar()} tarefa(s) pela metade")
    while True:
        if oauth.conectado("ml", "bling"):  # sem conta conectada não há o que sincronizar
            for t, intervalo in PERIODICAS.items():
                fila.disparar_periodica(t, intervalo)
        if not fila.processar_pendentes(HANDLERS):
            time.sleep(1)
