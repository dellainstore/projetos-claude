"""Configurações do módulo produtos — lidas do ambiente / Django settings."""
import os
from pathlib import Path

try:
    from django.conf import settings as django_settings
    PRODUTOS_DB_PATH = getattr(django_settings, "PRODUTOS_DB_PATH", None)
except Exception:
    PRODUTOS_DB_PATH = None

DB_PATH: str = PRODUTOS_DB_PATH or os.getenv(
    "PRODUTOS_DB_PATH",
    "/var/www/della-sistemas/projetos-claude/della_sistemas/data/produtos/inclusoes.db",
)

BLING_AUTH_DIR: str = os.getenv(
    "BLING_AUTH_DIR",
    "/var/www/della-sistemas/shared/bling_auth",
)

BLING_BASE_URL = "https://api.bling.com.br/Api/v3"
BLING_DEPOSITO_ID: str = (
    os.getenv("BLING_DEPOSITO_ID", "").strip()
    or os.getenv("DEPOSITO_ID", "").strip()
)

# Depósitos Bling disponíveis para escolha na tela "Incluir Estoque".
# IDs confirmados via GET /depositos da API Bling em 2026-08-28.
# O primeiro (Show Room - Della) é o padrão — mesmo ID de BLING_DEPOSITO_ID.
DEPOSITOS_DISPONIVEIS: list[dict] = [
    {"id": 7521173180, "nome": "Show Room - Della"},
    {"id": 14558196633, "nome": "Loja Anacã - São Paulo"},
    {"id": 9360683985, "nome": "Show Room - Londrina"},
]

DEFAULT_SUPPLIERS = [
    "MARIA EDENE",
    "IVONEIDE",
    "LINDACI",
    "POLI",
    "ADRIANA LUQUE",
    "DIVINA SANTA",
    "RAUL",
    "DETE",
]
