import psycopg

from app import config


def conectar() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)
