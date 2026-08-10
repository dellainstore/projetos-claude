import io
from datetime import date, timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import Afastamento, Colaborador, GozoFerias, PeriodoAquisitivo
from apps.rh.services.ferias import data_fim_gozo, data_retorno_gozo, garantir_proximo_periodo, resumo_periodo
from apps.rh.services.utils import parse_int


def _parse_data(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _sincronizar_afastamento_ferias(gozo: GozoFerias, usuario) -> None:
    """Cria/atualiza o Afastamento (dia inteiro, tipo férias) vinculado ao gozo,
    para que os dias lançados aqui dispensem a batida de ponto automaticamente —
    igual ao lançamento feito em Afastamentos."""
    from apps.rh.services.notificacoes import gerar_pendencias_do_dia

    fim = data_fim_gozo(gozo.data_inicio, gozo.dias)
    if gozo.afastamento_id:
        af = gozo.afastamento
        af.colaborador = gozo.periodo.colaborador
        af.data_inicio = gozo.data_inicio
        af.data_fim = fim
        af.observacao = gozo.observacao
        af.save(update_fields=["colaborador", "data_inicio", "data_fim", "observacao"])
    else:
        af = Afastamento.objects.create(
            colaborador=gozo.periodo.colaborador, tipo="ferias",
            data_inicio=gozo.data_inicio, data_fim=fim, dia_inteiro=True,
            remunerado=True, periodo_ferias=gozo.periodo,
            observacao=gozo.observacao, criado_por=usuario,
        )
        gozo.afastamento = af
        gozo.save(update_fields=["afastamento"])

    dia = gozo.data_inicio
    while dia <= fim:
        gerar_pendencias_do_dia(dia)
        dia += timedelta(days=1)


@perm_required("rh.gerir")
def view_ferias(request: HttpRequest) -> HttpResponse:
    # Pró-labore não tem direito a férias — não entra na lista deste módulo.
    colaboradores = list(
        Colaborador.objects.filter(ativo=True).exclude(tipo_contrato="pro_labore").order_by("nome")
    )
    colaborador_id = parse_int(request.GET.get("colaborador"), colaboradores[0].id if colaboradores else 0)
    colaborador = next((c for c in colaboradores if c.id == colaborador_id), None)

    periodos = []
    editando_periodo = None
    editando_gozo = None
    if colaborador:
        # Regra fixa: ao completar o período, o sistema já abre o próximo.
        garantir_proximo_periodo(colaborador)
        for p in colaborador.periodos_ferias.order_by("-inicio"):
            periodos.append(resumo_periodo(p))

        editar_periodo_id = parse_int(request.GET.get("editar_periodo"), 0)
        if editar_periodo_id:
            editando_periodo = next((r["periodo"] for r in periodos if r["periodo"].id == editar_periodo_id), None)

        editar_gozo_id = parse_int(request.GET.get("editar_gozo"), 0)
        if editar_gozo_id:
            for r in periodos:
                editando_gozo = next((g for g in r["gozos"] if g.id == editar_gozo_id), None)
                if editando_gozo:
                    break

    return render(request, "rh/ferias.html", {
        "colaboradores": colaboradores,
        "colaborador": colaborador,
        "periodos": periodos,
        "editando_periodo": editando_periodo,
        "editando_gozo": editando_gozo,
    })


@perm_required("rh.gerir")
@require_POST
def view_periodo_novo(request: HttpRequest) -> HttpResponse:
    colab = get_object_or_404(Colaborador, pk=request.POST.get("colaborador"))
    inicio = request.POST.get("inicio")
    fim = request.POST.get("fim")
    dias = parse_int(request.POST.get("dias_direito"), 30)
    if not inicio or not fim:
        messages.error(request, "Informe início e fim do período aquisitivo.")
    else:
        PeriodoAquisitivo.objects.create(
            colaborador=colab, inicio=inicio, fim=fim, dias_direito=dias,
            observacao=request.POST.get("observacao", "").strip(),
        )
        messages.success(request, "Período aquisitivo cadastrado.")
    return redirect(f"/rh/ferias/?colaborador={colab.id}")


@perm_required("rh.gerir")
@require_POST
def view_periodo_salvar(request: HttpRequest, pk: int) -> HttpResponse:
    periodo = get_object_or_404(PeriodoAquisitivo, pk=pk)
    inicio = request.POST.get("inicio")
    fim = request.POST.get("fim")
    dias = parse_int(request.POST.get("dias_direito"), 30)
    if not inicio or not fim:
        messages.error(request, "Informe início e fim do período aquisitivo.")
        return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}&editar_periodo={pk}")
    periodo.inicio = inicio
    periodo.fim = fim
    periodo.dias_direito = dias
    periodo.observacao = request.POST.get("observacao", "").strip()
    periodo.save(update_fields=["inicio", "fim", "dias_direito", "observacao"])
    messages.success(request, "Período aquisitivo atualizado.")
    return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}")


@perm_required("rh.gerir")
@require_POST
def view_periodo_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    periodo = get_object_or_404(PeriodoAquisitivo, pk=pk)
    colab_id = periodo.colaborador_id
    periodo.delete()
    messages.success(request, "Período removido.")
    return redirect(f"/rh/ferias/?colaborador={colab_id}")


@perm_required("rh.gerir")
@require_POST
def view_abono_salvar(request: HttpRequest, pk: int) -> HttpResponse:
    """Lança/atualiza o abono pecuniário (venda de férias). Só liberado quando o
    período está completo."""
    periodo = get_object_or_404(PeriodoAquisitivo, pk=pk)
    resumo = resumo_periodo(periodo)
    if not resumo["completo"]:
        messages.error(request, "O abono só pode ser lançado após o período completar 30 dias.")
        return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}")
    periodo.abono_dias = max(parse_int(request.POST.get("abono_dias"), 0), 0)
    periodo.abono_data_pagamento = request.POST.get("abono_data_pagamento") or None
    periodo.save(update_fields=["abono_dias", "abono_data_pagamento"])
    messages.success(request, f"Abono de {periodo.abono_dias} dia(s) registrado.")
    return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}")


@perm_required("rh.gerir")
@require_POST
def view_gozo_novo(request: HttpRequest) -> HttpResponse:
    periodo = get_object_or_404(PeriodoAquisitivo, pk=request.POST.get("periodo"))
    resumo = resumo_periodo(periodo)
    if not resumo["completo"]:
        messages.error(request, "Só é possível lançar férias após o período completar 30 dias.")
        return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}")
    data_inicio = _parse_data(request.POST.get("data_inicio"))
    dias = parse_int(request.POST.get("dias"), 1)
    if not data_inicio or dias < 1:
        messages.error(request, "Informe a data de início e a quantidade de dias.")
    else:
        gozo = GozoFerias.objects.create(
            periodo=periodo, data_inicio=data_inicio, dias=dias,
            observacao=request.POST.get("observacao", "").strip(),
        )
        _sincronizar_afastamento_ferias(gozo, request.user)
        messages.success(request, f"{dias} dia(s) de férias lançado(s).")
    return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}")


@perm_required("rh.gerir")
@require_POST
def view_gozo_salvar(request: HttpRequest, pk: int) -> HttpResponse:
    gozo = get_object_or_404(GozoFerias, pk=pk)
    colab_id = gozo.periodo.colaborador_id
    data_inicio = _parse_data(request.POST.get("data_inicio"))
    dias = parse_int(request.POST.get("dias"), 1)
    if not data_inicio or dias < 1:
        messages.error(request, "Informe a data de início e a quantidade de dias.")
        return redirect(f"/rh/ferias/?colaborador={colab_id}&editar_gozo={pk}")
    gozo.data_inicio = data_inicio
    gozo.dias = dias
    gozo.observacao = request.POST.get("observacao", "").strip()
    gozo.save(update_fields=["data_inicio", "dias", "observacao"])
    _sincronizar_afastamento_ferias(gozo, request.user)
    messages.success(request, "Lançamento de férias atualizado.")
    return redirect(f"/rh/ferias/?colaborador={colab_id}")


@perm_required("rh.gerir")
@require_POST
def view_gozo_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    gozo = get_object_or_404(GozoFerias, pk=pk)
    colab_id = gozo.periodo.colaborador_id
    af = gozo.afastamento
    gozo.delete()
    if af:
        af.delete()
    messages.success(request, "Lançamento de férias removido.")
    return redirect(f"/rh/ferias/?colaborador={colab_id}")


@perm_required("rh.gerir")
def htmx_preview_gozo(request: HttpRequest) -> HttpResponse:
    """Preview ao vivo (HTMX) de fim + retorno enquanto a gestora preenche
    início e dias, antes de salvar o lançamento de férias."""
    periodo = PeriodoAquisitivo.objects.filter(
        pk=parse_int(request.GET.get("periodo"), 0)
    ).select_related("colaborador").first()
    dias = parse_int(request.GET.get("dias"), 0)
    data_inicio_raw = request.GET.get("data_inicio", "")
    try:
        data_inicio = date.fromisoformat(data_inicio_raw) if data_inicio_raw else None
    except ValueError:
        data_inicio = None

    if not periodo or not data_inicio or dias < 1:
        return HttpResponse("")

    fim = data_fim_gozo(data_inicio, dias)
    retorno = data_retorno_gozo(periodo.colaborador, fim)
    return render(request, "rh/_ferias_preview_gozo.html", {
        "fim": fim, "retorno": retorno, "periodo_id": periodo.id,
    })


@perm_required("rh.gerir")
def view_ferias_pdf(request: HttpRequest) -> HttpResponse:
    """Relação de períodos aquisitivos de todos os colaboradores (para a diretoria)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from datetime import date

    cabecalho = ["Colaborador", "Período aquisitivo", "Direito", "Acumulado", "Gozados", "Abono", "Saldo", "Limite p/ Gozo"]
    linhas = [cabecalho]
    for c in Colaborador.objects.filter(ativo=True).order_by("nome"):
        for p in c.periodos_ferias.order_by("inicio"):
            r = resumo_periodo(p)
            linhas.append([
                c.nome,
                f"{p.inicio:%d/%m/%Y} a {p.fim:%d/%m/%Y}",
                str(p.dias_direito),
                str(r["dias_proporcionais"]),
                str(r["dias_gozados"]),
                str(r["abono"]),
                str(r["saldo"]),
                f"{r['limite_gozo']:%d/%m/%Y}" + (" (vencido)" if r["vencido"] else ""),
            ])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title="Relação de Férias")
    styles = getSampleStyleSheet()
    elementos = [
        Paragraph("Relação de Períodos Aquisitivos de Férias", styles["Title"]),
        Paragraph(f"Emitido em {date.today():%d/%m/%Y}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]
    if len(linhas) == 1:
        elementos.append(Paragraph("Nenhum período aquisitivo cadastrado.", styles["Normal"]))
    else:
        tabela = Table(linhas, repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9a96e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
            ("ALIGN", (2, 0), (6, -1), "CENTER"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#faf8f5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabela)
    doc.build(elementos)

    pdf = buffer.getvalue()
    buffer.close()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Relacao de Ferias - {date.today():%d-%m-%Y}.pdf"'
    return resp
