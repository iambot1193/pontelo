"""Cria um usuário de teste do Mercado Livre (vendedor ou comprador). Precisa do ML conectado.
Uso: docker compose exec api python -m scripts.ml_usuario_teste"""
from app.http import chamar

u = chamar("ml", "POST", "/users/test_user", json={"site_id": "MLB"})
print("id:", u.get("id"), "| apelido:", u.get("nickname"), "| e-mail:", u.get("email"), "| senha:", u.get("password"))
print("Guarde esses dados: o ML não mostra a senha de novo.")
