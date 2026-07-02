"""Helpers compartilhados entre as views do RH."""

from datetime import date
from decimal import Decimal, InvalidOperation


def competencia_opcoes(hoje: date | None = None) -> list[tuple[str, str]]:
    """Opções do seletor unificado mês/ano: 'AAAA-MM' → 'Jun/2026'.
    De Jan/2026 até Dez do ano seguinte ao atual."""
    from apps.metas.services.relatorio import MESES_PT
    hoje = hoje or date.today()
    return [
        (f"{ano}-{mes:02d}", f"{MESES_PT[mes]}/{ano}")
        for ano in range(2026, hoje.year + 2)
        for mes in range(1, 13)
    ]


def parse_competencia(request, hoje: date | None = None) -> tuple[int, int]:
    """Lê o seletor unificado `competencia` ('AAAA-MM'); cai nos parâmetros
    separados `ano`/`mes` (compatibilidade) e, por fim, no mês atual."""
    hoje = hoje or date.today()
    raw = request.GET.get("competencia", "")
    if raw and "-" in raw:
        a, _, m = raw.partition("-")
        if a.isdigit() and m.isdigit():
            return int(a), int(m)
    return parse_int(request.GET.get("ano"), hoje.year), parse_int(request.GET.get("mes"), hoje.month)


def parse_decimal(raw: str, default: Decimal = Decimal("0")) -> Decimal:
    """Aceita formato BR ('1.500,50') e US ('1500.50')."""
    raw = (raw or "").strip()
    if not raw:
        return default
    if "," in raw:  # vírgula = separador decimal BR; ponto = milhar
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return default


def parse_int(raw: str, default: int = 0) -> int:
    raw = (raw or "").strip()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default
