"""Helpers compartilhados entre as views do RH."""

from datetime import date
from decimal import Decimal, InvalidOperation


def competencia_opcoes(hoje: date | None = None, desde: date | None = None) -> list[tuple[str, str]]:
    """Opções do seletor unificado mês/ano: 'AAAA-MM' → 'Jun/2026'.
    De `desde` (mês/ano) até Dez do ano seguinte ao atual. Sem `desde`, cai no
    padrão Jan/2026 (início do painel). Telas de ponto passam
    `ParametrosPonto.get().data_inicio` — não faz sentido oferecer competência
    anterior ao início do controle de ponto, não tem batida nem apuração ali."""
    from apps.metas.services.relatorio import MESES_PT
    hoje = hoje or date.today()
    desde = desde or date(2026, 1, 1)
    opcoes = []
    for ano in range(desde.year, hoje.year + 2):
        mes_ini = desde.month if ano == desde.year else 1
        for mes in range(mes_ini, 13):
            opcoes.append((f"{ano}-{mes:02d}", f"{MESES_PT[mes]}/{ano}"))
    return opcoes


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


def parse_mes_ano(raw: str) -> tuple[int, int] | None:
    """Lê o valor de um <input type="month"> ('AAAA-MM') → (ano, mes).
    None se vazio ou inválido."""
    raw = (raw or "").strip()
    a, sep, m = raw.partition("-")
    if not sep or not a.isdigit() or not m.isdigit():
        return None
    return int(a), int(m)


def parse_int(raw: str, default: int = 0) -> int:
    raw = (raw or "").strip()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


_DIAS_SEMANA_ABREV = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def dia_semana_abrev(d: date) -> str:
    """Abreviação PT-BR do dia da semana (Seg…Dom), pra colunas de tabela/PDF
    onde o nome completo (Segunda, Terça…) não cabe."""
    return _DIAS_SEMANA_ABREV[d.weekday()]


_CONECTIVOS_NOME = {"de", "da", "do", "das", "dos", "e"}


def nome_exibicao(nome: str) -> str:
    """Nome em Title Case para exibição (ex.: PDFs), mantendo conectivos
    (de/da/do/das/dos/e) em minúsculo: 'MICHELLE ALVES FERNANDES' → 'Michelle
    Alves Fernandes'."""
    partes = (nome or "").strip().split()
    return " ".join(
        p.lower() if p.lower() in _CONECTIVOS_NOME and i > 0 else p.capitalize()
        for i, p in enumerate(partes)
    )
