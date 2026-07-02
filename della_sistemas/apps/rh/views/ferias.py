import io

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import Colaborador, GozoFerias, PeriodoAquisitivo
from apps.rh.services.ferias import garantir_proximo_periodo, resumo_periodo
from apps.rh.services.utils import parse_int


@perm_required("rh.gerir")
def view_ferias(request: HttpRequest) -> HttpResponse:
    colaboradores = list(Colaborador.objects.filter(ativo=True).order_by("nome"))
    colaborador_id = parse_int(request.GET.get("colaborador"), colaboradores[0].id if colaboradores else 0)
    colaborador = next((c for c in colaboradores if c.id == colaborador_id), None)

    periodos = []
    if colaborador:
        # Regra fixa: ao completar o período, o sistema já abre o próximo.
        garantir_proximo_periodo(colaborador)
        for p in colaborador.periodos_ferias.order_by("-inicio"):
            periodos.append(resumo_periodo(p))

    return render(request, "rh/ferias.html", {
        "colaboradores": colaboradores,
        "colaborador": colaborador,
        "periodos": periodos,
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
    periodo.save(update_fields=["abono_dias"])
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
    data_inicio = request.POST.get("data_inicio")
    dias = parse_int(request.POST.get("dias"), 1)
    if not data_inicio or dias < 1:
        messages.error(request, "Informe a data de início e a quantidade de dias.")
    else:
        GozoFerias.objects.create(
            periodo=periodo, data_inicio=data_inicio, dias=dias,
            observacao=request.POST.get("observacao", "").strip(),
        )
        messages.success(request, f"{dias} dia(s) de férias lançado(s).")
    return redirect(f"/rh/ferias/?colaborador={periodo.colaborador_id}")


@perm_required("rh.gerir")
@require_POST
def view_gozo_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    gozo = get_object_or_404(GozoFerias, pk=pk)
    colab_id = gozo.periodo.colaborador_id
    gozo.delete()
    messages.success(request, "Lançamento de férias removido.")
    return redirect(f"/rh/ferias/?colaborador={colab_id}")


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
