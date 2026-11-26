import psycopg
import redis
from fastapi import FastAPI

from app import admin, config, oauth, webhooks

app = FastAPI(title="pontelo")
app.include_router(admin.router)
app.include_router(oauth.router)
app.include_router(webhooks.router)


@app.get("/saude")
def saude():
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute("SELECT 1")
    redis.from_url(config.REDIS_URL).ping()
    return {"ok": True}
