"""Filtros padronizados do RH: período (mês atual / anterior / personalizado) e
seleção de colaboradoras (1, 2 ou todas).

Compartilhado por Salários, Comissão e Benefícios para manter o mesmo comportamento:
período sempre de mês a mês, somando vários meses quando a faixa é maior que um mês.
"""

from dataclasses import dataclass
from datetime import date

from apps.metas.services.relatorio import MESES_PT, _iter_months


def _mes_passado(hoje: date) -> tuple[int, int]:
    if hoje.month == 1:
        return hoje.year - 1, 12
    return hoje.year, hoje.month - 1


def _add_months(ano: int, mes: int, n: int) -> tuple[int, int]:
    m = mes + n
    a = ano + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return a, m


def _label(ano_ini, mes_ini, ano_fim, mes_fim) -> str:
    if (ano_ini, mes_ini) == (ano_fim, mes_fim):
        return f"{MESES_PT[mes_ini]}/{ano_ini}"
    return f"{MESES_PT[mes_ini]}/{ano_ini} a {MESES_PT[mes_fim]}/{ano_fim}"


@dataclass
class Periodo:
    filtro: str
    ano_ini: int
    mes_ini: int
    ano_fim: int
    mes_fim: int
    meses: list[tuple[int, int]]
    label: str

    @property
    def primeiro_dia(self) -> date:
        return date(self.ano_ini, self.mes_ini, 1)

    @property
    def ultimo_dia(self) -> date:
        import calendar
        return date(self.ano_fim, self.mes_fim, calendar.monthrange(self.ano_fim, self.mes_fim)[1])


def parse_periodo(request) -> Periodo:
    """Lê os parâmetros de período do request (GET). Faixa máxima de 12 meses."""
    hoje = date.today()
    ano_atual, mes_atual = hoje.year, hoje.month
    ano_ant, mes_ant = _mes_passado(hoje)

    filtro = request.GET.get("filtro", "atual")
    if filtro == "passado":
        ano_ini = ano_fim = ano_ant
        mes_ini = mes_fim = mes_ant
    elif filtro == "custom":
        # Campo combinado "AAAA-MM" (periodo_ini/periodo_fim); aceita também os
        # parâmetros separados antigos (ano_ini/mes_ini) como fallback.
        def _ym(combinado_key, ano_key, mes_key, def_a, def_m):
            raw = request.GET.get(combinado_key, "")
            if raw and "-" in raw:
                a, _, m = raw.partition("-")
                if a.isdigit() and m.isdigit():
                    return int(a), int(m)
            try:
                return int(request.GET.get(ano_key, def_a)), int(request.GET.get(mes_key, def_m))
            except (TypeError, ValueError):
                return def_a, def_m
        ano_ini, mes_ini = _ym("periodo_ini", "ano_ini", "mes_ini", ano_atual, mes_atual)
        ano_fim, mes_fim = _ym("periodo_fim", "ano_fim", "mes_fim", ano_ini, mes_ini)
        if (ano_fim, mes_fim) < (ano_ini, mes_ini):
            ano_fim, mes_fim = ano_ini, mes_ini
        max_a, max_m = _add_months(ano_ini, mes_ini, 11)
        if (ano_fim, mes_fim) > (max_a, max_m):
            ano_fim, mes_fim = max_a, max_m
    else:
        filtro = "atual"
        ano_ini = ano_fim = ano_atual
        mes_ini = mes_fim = mes_atual

    meses = list(_iter_months(ano_ini, mes_ini, ano_fim, mes_fim))
    return Periodo(
        filtro=filtro, ano_ini=ano_ini, mes_ini=mes_ini,
        ano_fim=ano_fim, mes_fim=mes_fim, meses=meses,
        label=_label(ano_ini, mes_ini, ano_fim, mes_fim),
    )


def parse_colaboradores(request, queryset):
    """Filtra o queryset pelas colaboradoras marcadas (param repetido `colaborador`).

    Retorna (queryset_filtrado, ids_selecionados:set[int]). Sem seleção = todas.
    """
    raw = request.GET.getlist("colaborador")
    ids = {int(x) for x in raw if x.isdigit()}
    if ids:
        queryset = queryset.filter(id__in=ids)
    return queryset, ids


def _periodo_opcoes(hoje: date) -> list[tuple[str, str]]:
    """Opções do campo combinado mês/ano: 'AAAA-MM' → 'Jun/2026'.
    De Jan/2026 até Dez do ano seguinte ao atual."""
    opcoes = []
    for ano in range(2026, hoje.year + 2):
        for mes in range(1, 13):
            opcoes.append((f"{ano}-{mes:02d}", f"{MESES_PT[mes]}/{ano}"))
    return opcoes


def contexto_filtro(request, colaboradores_qs) -> dict:
    """Monta o contexto comum do partial `rh/_filtros.html`."""
    periodo = parse_periodo(request)
    _, ids_sel = parse_colaboradores(request, colaboradores_qs)
    hoje = date.today()
    return {
        "periodo": periodo,
        "colaboradores_filtro": list(colaboradores_qs),
        "ids_selecionados": ids_sel,
        "periodo_opcoes": _periodo_opcoes(hoje),
        "periodo_ini_val": f"{periodo.ano_ini}-{periodo.mes_ini:02d}",
        "periodo_fim_val": f"{periodo.ano_fim}-{periodo.mes_fim:02d}",
    }
