from datetime import date
from decimal import Decimal

from django.http import HttpResponse
from django.utils.html import format_html
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.db.models import Sum

from apps.core.decorators import perm_required
from apps.pedidos.models import BaixaPedido, ParcelaPedido, PedidoBling
from apps.pedidos.services.formas_pagamento import FORMAS_PAGAMENTO
from apps.pedidos.services.situacoes import ATENDIDO_IDS

INICIO_2026 = date(2026, 1, 1)
_NUM_COLS = 9

_CHIPS_FORMA = ["PIX", "STONE", "PAG SEGURO", "Dinheiro", "Cheque", "TIK TOK"]
_FORMAS_LISTA = sorted(FORMAS_PAGAMENTO.values())


@perm_required("pedidos.ver")
def view_pagamentos_pendentes(request):
    pedidos = PedidoBling.objects.filter(
        situacao_id__in=list(ATENDIDO_IDS.keys()),
        data_pedido__gte=INICIO_2026,
        baixa__isnull=True,
        is_permuta=False,
    ).prefetch_related("parcelas").order_by("-data_pedido", "-bling_id")

    formas_baixas = list(
        BaixaPedido.objects.exclude(forma_efetiva="")
        .values_list("forma_efetiva", flat=True).distinct()
    )
    formas_corrigidas = list(
        PedidoBling.objects.exclude(forma_corrigida="").exclude(forma_corrigida__isnull=True)
        .values_list("forma_corrigida", flat=True).distinct()
    )
    formas = sorted(set(formas_baixas + formas_corrigidas))

    hoje = date.today()

    return render(request, "pedidos/pagamentos_pendentes.html", {
        "pedidos": pedidos,
        "total": pedidos.count(),
        "formas_disponiveis": formas,
        "chips_forma": _CHIPS_FORMA,
        "formas_lista": _FORMAS_LISTA,
        "hoje": hoje,
    })


@perm_required("pedidos.ver")
def view_pagamentos_confirmados(request):
    baixas = BaixaPedido.objects.select_related(
        "pedido", "confirmado_por"
    ).prefetch_related(
        "pedido__parcelas"
    ).filter(
        pedido__data_pedido__gte=INICIO_2026,
    ).order_by("-confirmado_em")

    return render(request, "pedidos/pagamentos_confirmados.html", {
        "baixas": baixas,
        "total": baixas.count(),
        "chips_forma": _CHIPS_FORMA,
    })


@perm_required("pedidos.ver")
def view_pagamentos_resumo(request):
    hoje = date.today()

    pedidos_base = PedidoBling.objects.filter(
        situacao_id__in=list(ATENDIDO_IDS.keys()),
        data_pedido__gte=INICIO_2026,
        baixa__isnull=True,
        is_permuta=False,
    ).prefetch_related("parcelas").order_by("-data_pedido", "-bling_id")

    total_atraso = Decimal("0")
    total_futuro = Decimal("0")
    # lista de (pedido, valor_em_atraso, data_mais_antiga_vencida) para o template
    pedidos_atraso: list[tuple] = []

    for pedido in pedidos_base:
        parcelas = [p for p in pedido.parcelas.all() if not p.baixada]

        if parcelas:
            valor_atraso = Decimal("0")
            min_data: date | None = None
            for parc in parcelas:
                if parc.data_vencimento and parc.data_vencimento < hoje:
                    valor_atraso += parc.valor
                    total_atraso += parc.valor
                    if min_data is None or parc.data_vencimento < min_data:
                        min_data = parc.data_vencimento
                else:
                    total_futuro += parc.valor
            if min_data is not None:
                pedidos_atraso.append((pedido, valor_atraso, min_data))
        else:
            ref_date = pedido.data_corrigida or pedido.data_pagamento
            if ref_date and ref_date < hoje:
                total_atraso += pedido.valor_total
                pedidos_atraso.append((pedido, pedido.valor_total, ref_date))
            else:
                total_futuro += pedido.valor_total

    # Mais atrasado primeiro (data de vencimento mais antiga)
    pedidos_atraso.sort(key=lambda x: x[2])

    # Total já confirmado/pago no ano
    total_pago = BaixaPedido.objects.filter(
        pedido__data_pedido__gte=INICIO_2026,
        pedido__is_permuta=False,
    ).aggregate(total=Sum("pedido__valor_total"))["total"] or Decimal("0")

    return render(request, "pedidos/pagamentos_resumo.html", {
        "total_pago": total_pago,
        "total_atraso": total_atraso,
        "total_futuro": total_futuro,
        "pedidos_atraso": pedidos_atraso,
        "hoje": hoje,
        "total_pedidos_pendentes": pedidos_base.count(),
    })


@perm_required("pedidos.baixar")
@require_POST
def view_dar_baixa(request, pedido_id: int):
    pedido = get_object_or_404(PedidoBling, pk=pedido_id)

    forma_raw = (request.POST.get("forma_conferida") or "").strip()
    data_raw  = (request.POST.get("data_conferida") or "").strip()

    forma_efetiva = forma_raw or pedido.forma_corrigida or pedido.forma_pagamento
    try:
        data_efetiva = date.fromisoformat(data_raw) if data_raw else (pedido.data_corrigida or pedido.data_pagamento)
    except ValueError:
        data_efetiva = pedido.data_corrigida or pedido.data_pagamento

    if forma_raw and forma_raw != pedido.forma_pagamento:
        pedido.forma_corrigida = forma_raw
    if data_efetiva and data_efetiva != pedido.data_pagamento:
        pedido.data_corrigida = data_efetiva
    pedido.save(update_fields=["forma_corrigida", "data_corrigida"])

    _, criado = BaixaPedido.objects.get_or_create(
        pedido=pedido,
        defaults={
            "confirmado_por": request.user,
            "observacao": request.POST.get("observacao", ""),
            "forma_efetiva": forma_efetiva or "",
            "data_efetiva": data_efetiva,
        },
    )

    # Marca todas as parcelas pendentes como baixadas
    pedido.parcelas.filter(baixada=False).update(
        baixada=True,
        baixada_por=request.user,
        baixada_em=timezone.now(),
        forma_efetiva=forma_efetiva or "",
        data_efetiva=data_efetiva,
    )

    msg = "Baixa confirmada" if criado else "já havia sido baixado"
    color = "#166534" if criado else "#6b7280"
    return HttpResponse(format_html(
        '<tbody id="grupo-pedido-{}">'
        '<tr class="pedido-baixado">'
        '<td colspan="{}" style="text-align:center;color:{};padding:.75rem;font-weight:600;">'
        '&#10003; {} — Pedido #{}'
        '</td></tr></tbody>',
        pedido_id, _NUM_COLS, color, msg, pedido.numero,
    ))


@perm_required("pedidos.baixar")
@require_POST
def view_dar_baixa_parcela(request, parcela_id: int):
    parcela = get_object_or_404(ParcelaPedido, pk=parcela_id)
    pedido = parcela.pedido
    total_parcelas = pedido.parcelas.count()

    if not parcela.baixada:
        forma_raw = (request.POST.get("forma_conferida") or "").strip()
        data_raw  = (request.POST.get("data_conferida") or "").strip()
        try:
            data_ef = date.fromisoformat(data_raw) if data_raw else parcela.data_vencimento
        except ValueError:
            data_ef = parcela.data_vencimento
        parcela.baixada = True
        parcela.baixada_por = request.user
        parcela.baixada_em = timezone.now()
        parcela.forma_efetiva = forma_raw or parcela.forma_pagamento
        parcela.data_efetiva = data_ef
        parcela.save()

    parcela_row = format_html(
        '<tr id="row-parcela-{}" class="pedido-baixado">'
        '<td colspan="{}" style="text-align:center;color:#166534;'
        'padding:.4rem;font-size:.82rem;font-style:italic;">'
        '&#10003; Parcela {}/{} baixada'
        '</td></tr>',
        parcela_id, _NUM_COLS, parcela.numero, total_parcelas,
    )

    todas_baixadas = not pedido.parcelas.filter(baixada=False).exists()

    if todas_baixadas:
        BaixaPedido.objects.get_or_create(
            pedido=pedido,
            defaults={
                "confirmado_por": request.user,
                "observacao": "Baixa automática — todas as parcelas baixadas individualmente",
                "forma_efetiva": pedido.forma_corrigida or pedido.forma_pagamento or "",
                "data_efetiva": pedido.data_corrigida or pedido.data_pagamento,
            },
        )
        oob = format_html(
            '<tbody id="grupo-pedido-{}" hx-swap-oob="true">'
            '<tr class="pedido-baixado">'
            '<td colspan="{}" style="text-align:center;color:#166534;padding:.75rem;font-weight:600;">'
            '&#10003; Pedido #{} — todas as parcelas baixadas'
            '</td></tr></tbody>',
            pedido.pk, _NUM_COLS, pedido.numero,
        )
        return HttpResponse(parcela_row + "\n" + oob)

    return HttpResponse(parcela_row)


@perm_required("pedidos.ver")
@require_POST
def view_salvar_correcao(request, pedido_id: int):
    pedido = get_object_or_404(PedidoBling, pk=pedido_id)

    forma_raw = (request.POST.get("forma_conferida") or "").strip()
    data_raw  = (request.POST.get("data_conferida") or "").strip()

    update_fields = []
    if forma_raw:
        pedido.forma_corrigida = forma_raw
        update_fields.append("forma_corrigida")
    if data_raw:
        try:
            pedido.data_corrigida = date.fromisoformat(data_raw)
            update_fields.append("data_corrigida")
        except ValueError:
            pass

    if update_fields:
        pedido.save(update_fields=update_fields)

    return HttpResponse(
        f'<span id="status-correcao-{pedido_id}" '
        f'style="color:#166534;font-size:.8rem;font-weight:600;">&#10003; Salvo</span>'
    )
