from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.pedidos.models import PedidoBling
from apps.rh.models import Colaborador, ComissaoLog, ComissaoPedido
from apps.rh.services.comissao import linhas_comissao_periodo
from apps.rh.services.filtros import contexto_filtro, parse_colaboradores, parse_periodo
from apps.rh.services.utils import parse_decimal


def _vendedoras_qs():
    return Colaborador.objects.filter(
        ativo=True, recebe_comissao=True, bling_vendedor_id__isnull=False
    ).order_by("nome")


def _dono_conflitante(pedido: PedidoBling, colaborador: Colaborador) -> str | None:
    """Nome de OUTRA vendedora que já tem esse pedido na comissão (vendedor natural
    do Bling ou override manual), se houver. Um pedido não pode contar em dobro."""
    if pedido.vendedor_id:
        outra = _vendedoras_qs().exclude(id=colaborador.id).filter(
            bling_vendedor_id=pedido.vendedor_id
        ).first()
        if outra:
            return outra.nome
    outra_ov = (
        ComissaoPedido.objects.filter(pedido=pedido)
        .exclude(colaborador=colaborador)
        .select_related("colaborador")
        .first()
    )
    return outra_ov.colaborador.nome if outra_ov else None


def _periodo_qs(periodo) -> str:
    return urlencode({
        "filtro": periodo.filtro,
        "ano_ini": periodo.ano_ini, "mes_ini": periodo.mes_ini,
        "ano_fim": periodo.ano_fim, "mes_fim": periodo.mes_fim,
    })


@perm_required("rh.gerir")
def view_comissao(request: HttpRequest) -> HttpResponse:
    vendedoras = _vendedoras_qs()
    selecionadas, _ = parse_colaboradores(request, vendedoras)
    periodo = parse_periodo(request)

    secoes = []
    for v in selecionadas:
        d = linhas_comissao_periodo(v, periodo.meses)
        total_base = sum((l["base"] for l in d["linhas"] if l["valida"]), Decimal("0.00"))
        secoes.append({
            "colaborador": v,
            "linhas": d["linhas"],
            "total": d["total"],
            "total_base": total_base,
            "qtd_nao_pagos": sum(1 for l in d["linhas"] if not l["pago"]),
        })

    ctx = contexto_filtro(request, vendedoras)
    ctx.update({
        "secoes": secoes,
        "vendedoras": list(vendedoras),
        "periodo_qs": _periodo_qs(periodo),
    })
    return render(request, "rh/comissao.html", ctx)


@perm_required("rh.gerir")
@require_POST
def view_comissao_salvar(request: HttpRequest, colaborador_id: int, pedido_id: int) -> HttpResponse:
    """Salva o override de comissão de um pedido (HTMX), registra log e devolve a linha."""
    colaborador = get_object_or_404(Colaborador, pk=colaborador_id)
    pedido = get_object_or_404(PedidoBling, pk=pedido_id)

    base_raw = request.POST.get("base", "").strip()
    pct_raw = request.POST.get("percentual", "").strip()
    valida = request.POST.get("valida") == "on"

    valor_base = parse_decimal(base_raw) if base_raw else None
    percentual = parse_decimal(pct_raw) if pct_raw else None

    existing = ComissaoPedido.objects.filter(colaborador=colaborador, pedido=pedido).first()
    if existing:
        old_base, old_pct = existing.base_efetiva(), existing.percentual_efetivo()
    else:
        old_base, old_pct = pedido.valor_total, colaborador.comissao_percentual_padrao
    new_base = valor_base if valor_base is not None else pedido.valor_total
    new_pct = percentual if percentual is not None else colaborador.comissao_percentual_padrao

    obj, _ = ComissaoPedido.objects.update_or_create(
        colaborador=colaborador, pedido=pedido,
        defaults={
            "valor_base": valor_base, "percentual": percentual, "valida": valida,
            "manual": True, "alterado_por": request.user, "alterado_em": timezone.now(),
        },
    )

    if new_base != old_base:
        ComissaoLog.objects.create(
            comissao=obj, campo="base", de=str(old_base), para=str(new_base), usuario=request.user,
        )
    if new_pct != old_pct:
        ComissaoLog.objects.create(
            comissao=obj, campo="percentual", de=str(old_pct), para=str(new_pct), usuario=request.user,
        )

    linha = {
        "pedido": pedido,
        "data": pedido.data_pedido,
        "numero": pedido.numero or pedido.bling_id,
        "cliente": pedido.cliente_nome,
        "situacao": pedido.situacao_nome,
        "base": obj.base_efetiva(),
        "percentual": obj.percentual_efetivo(),
        "valor": obj.valor_comissao(),
        "valida": obj.valida,
        "manual": obj.manual,
        "pago": False,
    }
    return render(request, "rh/_comissao_linha.html", {
        "linha": linha, "colaborador": colaborador, "salvo": True,
    })


@perm_required("rh.gerir")
@require_POST
def view_comissao_incluir(request: HttpRequest) -> HttpResponse:
    """Inclui manualmente um pedido pelo número para uma vendedora (mesmo sem
    vendedor lançado no Bling)."""
    colaborador = get_object_or_404(Colaborador, pk=request.POST.get("colaborador"))
    numero = (request.POST.get("numero") or "").strip()

    pedido = PedidoBling.objects.filter(numero=numero).first()
    if pedido is None and numero.isdigit():
        pedido = PedidoBling.objects.filter(bling_id=int(numero)).first()

    if pedido is None:
        messages.error(request, f"Pedido nº {numero} não encontrado na base sincronizada.")
    elif (conflito := _dono_conflitante(pedido, colaborador)):
        messages.error(
            request,
            f"Pedido nº {numero} já está na comissão de {conflito} — "
            "um mesmo pedido não pode contar pra duas vendedoras.",
        )
    else:
        obj, created = ComissaoPedido.objects.get_or_create(
            colaborador=colaborador, pedido=pedido,
            defaults={"manual": True, "alterado_por": request.user, "alterado_em": timezone.now()},
        )
        if created:
            ComissaoLog.objects.create(
                comissao=obj, campo="inclusao", de="", para=numero, usuario=request.user,
            )
            messages.success(request, f"Pedido nº {numero} incluído para {colaborador.nome}.")
        else:
            messages.info(request, f"Pedido nº {numero} já estava na lista de {colaborador.nome}.")

    destino = f"{reverse('rh:comissao')}?{request.POST.get('querystring', '')}"
    return redirect(destino)


@perm_required("rh.gerir")
def view_comissao_pdf(request: HttpRequest, colaborador_id: int) -> HttpResponse:
    """Gera o PDF de comissão de uma vendedora no período (para envio/conferência)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    from apps.metas.services.relatorio import MESES_PT
    from apps.rh.services.utils import nome_exibicao

    colaborador = get_object_or_404(Colaborador, pk=colaborador_id)
    periodo = parse_periodo(request)
    dados = linhas_comissao_periodo(colaborador, periodo.meses)

    primeiro_nome = colaborador.nome.split()[0] if colaborador.nome else "vendedora"
    if len(periodo.meses) == 1:
        ref = f"{MESES_PT[periodo.mes_ini]}-{periodo.ano_ini}"
        ref_fname = f"{periodo.mes_ini:02d}-{periodo.ano_ini}"
    else:
        ref = periodo.label
        ref_fname = f"{periodo.mes_ini:02d}-{periodo.ano_ini} a {periodo.mes_fim:02d}-{periodo.ano_fim}"

    import io
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Comissão {primeiro_nome}")
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "TituloComissao", parent=styles["Title"], fontSize=15, leading=18, alignment=TA_CENTER,
    )
    nome_style = ParagraphStyle(
        "NomeComissao", parent=styles["Normal"], fontSize=12, leading=15,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    )
    referencia_style = ParagraphStyle(
        "ReferenciaComissao", parent=styles["Normal"], fontSize=9, leading=12,
        alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
    )
    elementos = [
        Paragraph("Comissão", titulo_style),
        Paragraph(nome_exibicao(colaborador.nome), nome_style),
        Paragraph(f"Referência: {ref}", referencia_style),
        Spacer(1, 0.5 * cm),
    ]

    def _brl(v) -> str:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    cabecalho = ["Data", "Nº Pedido", "Cliente", "Valor Pedido", "%", "Comissão", "Pago?"]
    linhas_tab = [cabecalho]
    total_base = Decimal("0.00")
    for l in dados["linhas"]:
        if not l["valida"]:
            continue
        total_base += l["base"]
        if l["comissao_parcelada"]:
            num_str = f'{l["numero"]} P{l["parcela_num"]}/{l["parcela_total"]}'
        else:
            num_str = str(l["numero"])
        if l["pago"]:
            pago_str = "Sim"
        elif l.get("parcial"):
            pago_str = "Parcial"
        else:
            pago_str = "NÃO"
        linhas_tab.append([
            l["data"].strftime("%d/%m/%Y"),
            num_str,
            (l["cliente"] or "")[:30],
            _brl(l["base"]),
            f'{l["percentual"]}%',
            _brl(l["valor"]),
            pago_str,
        ])
    linhas_tab.append(["", "", "", _brl(total_base), "", _brl(dados["total"]), ""])

    # Colorir células "Parcial" em laranja e "NÃO" em vermelho
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9a96e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -2), 0.4, colors.HexColor("#dddddd")),
        ("ALIGN", (3, 0), (6, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor("#faf8f5")),
    ]
    for row_idx, row in enumerate(linhas_tab[1:-1], start=1):
        pago_cell = row[-1]
        if pago_cell == "Parcial":
            style_cmds.append(("TEXTCOLOR", (6, row_idx), (6, row_idx), colors.HexColor("#d97706")))
            style_cmds.append(("FONTNAME", (6, row_idx), (6, row_idx), "Helvetica-Bold"))
        elif pago_cell == "NÃO":
            style_cmds.append(("TEXTCOLOR", (6, row_idx), (6, row_idx), colors.HexColor("#dc2626")))

    tabela = Table(linhas_tab, repeatRows=1)
    tabela.setStyle(TableStyle(style_cmds))
    elementos.append(tabela)
    doc.build(elementos)

    pdf = buffer.getvalue()
    buffer.close()
    filename = f"Comissão {primeiro_nome} ({ref_fname}).pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
