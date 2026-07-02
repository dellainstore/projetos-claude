"""Composição da folha de pagamento por colaboradora/mês.

A folha soma quatro blocos: salário fixo (Colaborador.salario_base), comissão válida
do mês, VT (puxado do mês adiantado — ver `vt_meses_adiantado`) e lançamentos manuais
(13º, adiantamento, outros).
"""

from decimal import Decimal

from apps.rh.models import BeneficioVT, EventoFolha, LancamentoRecorrente, PagamentoFolha
from apps.rh.services.beneficios import dias_vt_sugeridos
from apps.rh.services.comissao import linhas_comissao
from apps.rh.services.filtros import _add_months


def eventos_do_mes(colaborador, ano: int, mes: int) -> list[dict]:
    """Lançamentos do mês: avulsos (EventoFolha) + recorrências ativas.

    Cada item: tipo_display, descricao, valor, data (pagamento), recorrente, pk.
    Uma recorrência é ignorada se já houver um EventoFolha materializado dela no mês.
    """
    reais = list(EventoFolha.objects.filter(colaborador=colaborador, ano=ano, mes=mes))
    materializadas = {e.recorrencia_id for e in reais if e.recorrencia_id}
    itens = [
        {
            "tipo_display": e.get_tipo_display(), "descricao": e.descricao,
            "valor": e.valor, "data": e.data_pagamento, "natureza": e.natureza,
            "recorrente": e.recorrencia_id is not None, "pk": e.pk,
        }
        for e in reais
    ]
    for r in LancamentoRecorrente.objects.filter(colaborador=colaborador, ativo=True):
        if r.id in materializadas or not r.ativa_no_mes(ano, mes):
            continue
        itens.append({
            "tipo_display": r.get_tipo_display(), "descricao": r.descricao,
            "valor": r.valor, "data": r.data_no_mes(ano, mes), "natureza": r.natureza,
            "recorrente": True, "pk": None,
        })
    return itens


def vt_do_mes(colaborador, ano: int, mes: int) -> dict:
    """VT que entra no salário do mês X = VT do mês X + `vt_meses_adiantado`.

    Usa o BeneficioVT lançado para o mês de referência; se não houver, sugere a
    partir da escala/dias úteis e do valor-dia cadastrado na colaboradora.
    """
    if not colaborador.recebe_vt:
        return {
            "ref_ano": ano, "ref_mes": mes, "avanco": 0,
            "dias": 0, "valor_dia": Decimal("0"), "valor": Decimal("0.00"),
            "aplica": False,
        }
    avanco = colaborador.vt_meses_adiantado or 0
    ref_a, ref_m = _add_months(ano, mes, avanco)
    b = BeneficioVT.objects.filter(colaborador=colaborador, ano=ref_a, mes=ref_m).first()
    if b:
        dias, valor_dia, valor = b.dias, b.valor_dia, b.total()
    else:
        dias = dias_vt_sugeridos(colaborador, ref_a, ref_m)
        valor_dia = colaborador.vt_valor_dia
        valor = (Decimal(dias) * valor_dia).quantize(Decimal("0.01"))
    return {
        "ref_ano": ref_a, "ref_mes": ref_m, "avanco": avanco,
        "dias": dias, "valor_dia": valor_dia, "valor": valor, "aplica": True,
    }


def folha_mes(colaborador, ano: int, mes: int) -> dict:
    """Detalhamento da folha de uma colaboradora em um mês."""
    fixo = colaborador.salario_base
    recebe_comissao = colaborador.recebe_comissao and colaborador.bling_vendedor_id
    comissao = (
        linhas_comissao(colaborador, ano, mes)["total"]
        if recebe_comissao else Decimal("0.00")
    )
    vt = vt_do_mes(colaborador, ano, mes)
    eventos = eventos_do_mes(colaborador, ano, mes)

    datas = {
        p.componente: p.data_pagamento
        for p in PagamentoFolha.objects.filter(colaborador=colaborador, ano=ano, mes=mes)
    }
    vt["data"] = datas.get("vt")

    # ── Holerite: proventos (somam) × descontos (abatem) ──
    proventos = [{"label": "Salário", "valor": fixo, "data": datas.get("salario")}]
    if recebe_comissao:
        proventos.append({"label": "Comissão", "valor": comissao, "data": datas.get("comissao")})
    if vt["aplica"]:
        proventos.append({"label": "Vale-transporte", "valor": vt["valor"], "data": vt["data"]})
    descontos = []
    for e in eventos:
        rotulo = e["tipo_display"] + (f" — {e['descricao']}" if e["descricao"] else "")
        item = {"label": rotulo, "valor": e["valor"], "data": e["data"], "recorrente": e["recorrente"]}
        (descontos if e["natureza"] == "desconto" else proventos).append(item)

    total_proventos = sum((p["valor"] for p in proventos), Decimal("0"))
    total_descontos = sum((d["valor"] for d in descontos), Decimal("0"))
    # "extras" = saldo líquido dos lançamentos (provento - desconto), para o resumo.
    extras = sum((e["valor"] for e in eventos if e["natureza"] != "desconto"), Decimal("0")) \
        - sum((e["valor"] for e in eventos if e["natureza"] == "desconto"), Decimal("0"))
    total = total_proventos - total_descontos

    return {
        "ano": ano, "mes": mes,
        "fixo": fixo, "fixo_data": datas.get("salario"),
        "comissao": comissao, "comissao_data": datas.get("comissao"),
        "comissao_aplica": bool(recebe_comissao),
        "vt": vt,
        "eventos": eventos, "extras": extras,
        "proventos": proventos, "descontos": descontos,
        "total_proventos": total_proventos, "total_descontos": total_descontos,
        "total": total,
    }


def folha_periodo(colaborador, meses: list[tuple[int, int]]) -> dict:
    """Agrega a folha de uma colaboradora ao longo de vários meses (soma)."""
    detalhes = [folha_mes(colaborador, a, m) for a, m in meses]
    soma = lambda chave: sum((d[chave] for d in detalhes), Decimal("0"))  # noqa: E731
    fixo = soma("fixo")
    comissao = soma("comissao")
    vt = sum((d["vt"]["valor"] for d in detalhes), Decimal("0"))
    extras = soma("extras")
    return {
        "colaborador": colaborador,
        "detalhes": detalhes,
        "fixo": fixo, "comissao": comissao, "vt": vt, "extras": extras,
        "total": fixo + comissao + vt + extras,
    }
