"""Configurações do módulo Estoque (Análise) — lidas do ambiente / Django settings."""
import os
from pathlib import Path

try:
    from django.conf import settings as django_settings
except Exception:
    django_settings = None


def _setting(name: str, default):
    if django_settings is not None and hasattr(django_settings, name):
        return getattr(django_settings, name)
    return os.getenv(name, default)


DB_PATH: str = _setting(
    "ESTOQUE_DB_PATH",
    "/var/www/della-sistemas/projetos-claude/della_sistemas/data/estoque/estoque.db",
)

HISTORICO_CONSOLIDADO_XLSX_PATH: str = _setting(
    "ESTOQUE_HISTORICO_CONSOLIDADO_XLSX_PATH",
    "/var/www/della-sistemas/data/cmv_consolidado.xlsx",
)
HISTORICO_CONSOLIDADO_SHEET: str = _setting("ESTOQUE_HISTORICO_CONSOLIDADO_SHEET", "Produtos_Mensal")
HISTORICO_BASE_INICIO: str = _setting("ESTOQUE_HISTORICO_BASE_INICIO", "2025-01-01")

REPOSICAO_COBERTURA_ALVO_DIAS: int = int(_setting("ESTOQUE_REPOSICAO_COBERTURA_ALVO_DIAS", 30))
REPOSICAO_LOTE_MINIMO_MODELO_COR: int = int(_setting("ESTOQUE_REPOSICAO_LOTE_MINIMO_MODELO_COR", 12))
REPOSICAO_LOTE_MINIMO_SKU: int = int(_setting("ESTOQUE_REPOSICAO_LOTE_MINIMO_SKU", 6))
REPOSICAO_ARREDONDAR_MULTIPLO_LOTE: bool = str(
    _setting("ESTOQUE_REPOSICAO_ARREDONDAR_MULTIPLO_LOTE", "true")
).strip().lower() in {"1", "true", "yes", "y", "on"}
REPOSICAO_PESO_HISTORICO_TAMANHO: float = float(_setting("ESTOQUE_REPOSICAO_PESO_HISTORICO_TAMANHO", 0.50))
REPOSICAO_PESO_ESTOQUE_TAMANHO: float = float(_setting("ESTOQUE_REPOSICAO_PESO_ESTOQUE_TAMANHO", 0.30))
REPOSICAO_PESO_MIX_BASE_TAMANHO: float = float(_setting("ESTOQUE_REPOSICAO_PESO_MIX_BASE_TAMANHO", 0.20))


def _parse_mix_base(raw: str) -> dict[str, float]:
    default = {"PP": 0.10, "P": 0.25, "M": 0.30, "G": 0.20, "GG": 0.15}
    if not raw.strip():
        return default

    parsed: dict[str, float] = {}
    for part in raw.split(","):
        chunk = part.strip()
        if not chunk or ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        tamanho = key.strip().upper()
        try:
            pct = float(value.strip().replace(",", "."))
        except ValueError:
            continue
        if pct > 0:
            parsed[tamanho] = pct

    if not parsed:
        return default
    total = sum(parsed.values())
    if total <= 0:
        return default
    return {k: v / total for k, v in parsed.items()}


REPOSICAO_MIX_BASE_TAMANHO: dict[str, float] = _parse_mix_base(
    str(_setting("ESTOQUE_REPOSICAO_MIX_BASE_TAMANHO", "PP:0.10,P:0.25,M:0.30,G:0.20,GG:0.15"))
)

DATA_DIR = Path(DB_PATH).resolve().parent
LOG_DIR = Path(_setting("ESTOQUE_LOG_DIR", str(DATA_DIR))).resolve()
