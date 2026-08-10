from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.metas.services.relatorio import MESES_PT
from apps.rh.models import (
    NATUREZA_CHOICES,
    Colaborador,
    EventoFolha,
    LancamentoRecorrente,
    PagamentoFolha,
)
from apps.rh.services.filtros import contexto_filtro, parse_colaboradores, parse_periodo
from apps.rh.services.folha import folha_periodo
from apps.rh.services.utils import (
    competencia_opcoes,
    parse_competencia,
    parse_decimal,
    parse_int,
    parse_mes_ano,
)


@perm_required("rh.gerir")
def view_folha_resumo(request: HttpRequest) -> HttpResponse:
    """Resumo agrupado da folha no período: Fixo | Comissão | VT | Lançamentos | Total."""
    ativos = Colaborador.objects.filter(ativo=True, na_folha=True).order_by("nome")
    selecionados, _ = parse_colaboradores(request, ativos)
    periodo = parse_periodo(request)

    linhas = [folha_periodo(c, periodo.meses) for c in selecionados]
    totais = {
        "fixo": sum((l["fixo"] for l in linhas), Decimal("0")),
        "comissao": sum((l["comissao"] for l in linhas), Decimal("0")),
        "vt": sum((l["vt"] for l in linhas), Decimal("0")),
        "extras": sum((l["extras"] for l in linhas), Decimal("0")),
        "total": sum((l["total"] for l in linhas), Decimal("0")),
    }
    ctx = contexto_filtro(request, ativos)
    ctx.update({"linhas": linhas, "totais": totais})
    return render(request, "rh/folha_resumo.html", ctx)


@perm_required("rh.gerir")
def view_folha_detalhada(request: HttpRequest) -> HttpResponse:
    """Folha detalhada por colaboradora: mês a mês e item a item."""
    ativos = Colaborador.objects.filter(ativo=True, na_folha=True).order_by("nome")
    selecionados, _ = parse_colaboradores(request, ativos)
    periodo = parse_periodo(request)

    folhas = [folha_periodo(c, periodo.meses) for c in selecionados]
    # anexa o nome do mês em cada detalhe para o template
    for f in folhas:
        for d in f["detalhes"]:
            d["mes_nome"] = MESES_PT.get(d["mes"], "")
            d["vt"]["ref_mes_nome"] = MESES_PT.get(d["vt"]["ref_mes"], "")
    ctx = contexto_filtro(request, ativos)
    ctx.update({"folhas": folhas})
    return render(request, "rh/folha_detalhada.html", ctx)


@perm_required("rh.gerir")
def view_salarios(request: HttpRequest) -> HttpResponse:
    """Lançamento de eventos avulsos (13º, adiantamento, outros) por mês.

    Salário, VT e comissão são pagos no 5º dia útil; o restante entra por
    lançamento manual com a data informada. Abaixo, o histórico de lançamentos.
    """
    hoje = date.today()
    ano, mes = parse_competencia(request, hoje)

    colaboradores = list(
        Colaborador.objects.filter(ativo=True, na_folha=True).order_by("nome")
    )
    eventos = list(
        EventoFolha.objects.filter(ano=ano, mes=mes).select_related("colaborador")
    )
    recorrencias = list(
        LancamentoRecorrente.objects.filter(ativo=True).select_related("colaborador")
    )
    from apps.rh.services.calendario import enesimo_dia_util
    quinto = enesimo_dia_util(ano, mes, 5)
    quinto_iso = quinto.isoformat() if quinto else ""

    return render(request, "rh/salarios.html", {
        "eventos": eventos,
        "recorrencias": recorrencias,
        "quinto_dia_util": quinto_iso,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "meses_opcoes": competencia_opcoes(hoje),
        "colaboradores": colaboradores,
        "tipos_evento": EventoFolha.TIPO_CHOICES,
        "naturezas": NATUREZA_CHOICES,
    })


@perm_required("rh.gerir")
@require_POST
def view_evento_novo(request: HttpRequest) -> HttpResponse:
    ano = parse_int(request.POST.get("ano"), date.today().year)
    mes = parse_int(request.POST.get("mes"), date.today().month)
    colab = get_object_or_404(Colaborador, pk=request.POST.get("colaborador"))
    valor = parse_decimal(request.POST.get("valor", ""))
    tipo = request.POST.get("tipo", "outro")
    natureza = request.POST.get("natureza", "provento")
    if natureza not in dict(NATUREZA_CHOICES):
        natureza = "provento"
    descricao = request.POST.get("descricao", "").strip()
    data_pag = request.POST.get("data_pagamento") or None
    recorrente = request.POST.get("recorrente") == "on"

    if valor <= 0:
        messages.error(request, "Informe um valor maior que zero.")
    elif recorrente:
        dia = parse_int(request.POST.get("dia_pagamento"), 20)
        indefinido = request.POST.get("indefinido") == "on"
        fim = None if indefinido else parse_mes_ano(request.POST.get("fim_competencia", ""))
        LancamentoRecorrente.objects.create(
            colaborador=colab, natureza=natureza, tipo=tipo, valor=valor, descricao=descricao,
            dia_pagamento=max(1, min(dia, 31)),
            ano_inicio=ano, mes_inicio=mes,
            indefinido=indefinido,
            ano_fim=fim[0] if fim else None,
            mes_fim=fim[1] if fim else None,
        )
        messages.success(request, "Lançamento recorrente criado.")
    else:
        EventoFolha.objects.create(
            colaborador=colab, ano=ano, mes=mes, natureza=natureza, tipo=tipo, valor=valor,
            descricao=descricao, data_pagamento=data_pag,
        )
        messages.success(request, "Lançamento adicionado.")
    return redirect(f"{reverse('rh:salarios')}?ano={ano}&mes={mes}")


@perm_required("rh.gerir")
@require_POST
def view_evento_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    evento = get_object_or_404(EventoFolha, pk=pk)
    ano, mes = evento.ano, evento.mes
    evento.delete()
    messages.success(request, "Lançamento removido.")
    return redirect(f"{reverse('rh:salarios')}?ano={ano}&mes={mes}")


@perm_required("rh.gerir")
@require_POST
def view_recorrencia_encerrar(request: HttpRequest, pk: int) -> HttpResponse:
    """Encerra um lançamento recorrente definindo o mês/ano fim (não exclui o
    histórico já gerado). Para recorrências por tempo indeterminado."""
    rec = get_object_or_404(LancamentoRecorrente, pk=pk)
    ano = parse_int(request.POST.get("ano"), date.today().year)
    mes = parse_int(request.POST.get("mes"), date.today().month)
    fim = parse_mes_ano(request.POST.get("fim_competencia", ""))
    if fim:
        rec.indefinido = False
        rec.ano_fim, rec.mes_fim = fim
        rec.save(update_fields=["indefinido", "ano_fim", "mes_fim"])
        messages.success(request, f"Recorrência encerrada em {fim[1]:02d}/{fim[0]}.")
    else:
        messages.error(request, "Informe o mês e o ano de encerramento.")
    return redirect(f"{reverse('rh:salarios')}?ano={ano}&mes={mes}")


@perm_required("rh.gerir")
@require_POST
def view_recorrencia_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    rec = get_object_or_404(LancamentoRecorrente, pk=pk)
    rec.delete()
    ano = parse_int(request.POST.get("ano"), date.today().year)
    mes = parse_int(request.POST.get("mes"), date.today().month)
    messages.success(request, "Recorrência removida.")
    return redirect(f"{reverse('rh:salarios')}?ano={ano}&mes={mes}")


@perm_required("rh.gerir")
@require_POST
def view_pagamentos_salvar(request: HttpRequest) -> HttpResponse:
    """Salva as datas de pagamento dos componentes fixos (salário/comissão/VT)
    de cada colaboradora no mês."""
    ano = parse_int(request.POST.get("ano"), date.today().year)
    mes = parse_int(request.POST.get("mes"), date.today().month)
    salvos = 0
    for c in Colaborador.objects.filter(ativo=True):
        for comp, _label in PagamentoFolha.COMPONENTE_CHOICES:
            raw = request.POST.get(f"{comp}_{c.id}") or ""
            if raw:
                PagamentoFolha.objects.update_or_create(
                    colaborador=c, ano=ano, mes=mes, componente=comp,
                    defaults={"data_pagamento": raw},
                )
                salvos += 1
            else:
                PagamentoFolha.objects.filter(
                    colaborador=c, ano=ano, mes=mes, componente=comp
                ).delete()
    messages.success(request, f"Datas de pagamento salvas ({salvos}).")
    return redirect(f"{reverse('rh:salarios')}?ano={ano}&mes={mes}")
