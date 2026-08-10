"""Cálculo de comissão a partir dos pedidos atendidos do Bling.

Regras:
- Pedidos pagos integralmente (BaixaPedido) → linha única no mês do pedido.
- Comissão > COMISSAO_PARCELAMENTO_LIMITE com parcelas (PIX parcelado) → uma linha
  por parcela, atribuída ao mês de competência determinado pela data de baixa e a
  regra do 5° dia útil:
    * Baixa até o 5° DU do mês → competência = esse mês
    * Baixa após o 5° DU       → competência = mês seguinte
- Parcelas ainda não baixadas ficam no mês do vencimento.
- Londrina não entra na comissão (ver ATENDIDO_COMISSAO_IDS).
"""

from datetime import date, timedelta
from decimal import Decimal

from apps.pedidos.models import BaixaPedido, ParcelaPedido, PedidoBling
from apps.pedidos.services.situacoes import ATENDIDO_COMISSAO_IDS
from apps.rh.models import ComissaoPedido

COMISSAO_PARCELAMENTO_LIMITE = Decimal("5000.00")


def _intervalo_mes(ano: int, mes: int) -> tuple[date, date]:
    inicio = date(ano, mes, 1)
    if mes == 12:
        fim = date(ano, 12, 31)
    else:
        fim = date(ano, mes + 1, 1) - timedelta(days=1)
    return inicio, fim


def _5o_dia_util(ano: int, mes: int) -> date:
    """Retorna o 5° dia útil (Seg-Sex) do mês."""
    count = 0
    d = date(ano, mes, 1)
    while True:
        if d.weekday() < 5:
            count += 1
            if count == 5:
                return d
        d += timedelta(days=1)


def _mes_competencia(baixa_date: date) -> tuple[int, int]:
    """Mês de competência da comissão conforme regra do 5° dia útil."""
    quinto = _5o_dia_util(baixa_date.year, baixa_date.month)
    if baixa_date <= quinto:
        return baixa_date.year, baixa_date.month
    if baixa_date.month == 12:
        return baixa_date.year + 1, 1
    return baixa_date.year, baixa_date.month + 1


def _pagamento_status(pedido_ids: list[int]) -> dict[int, str]:
    """Retorna 'pago', 'parcial' ou 'nao_pago' para cada pedido."""
    if not pedido_ids:
        return {}
    result = {pid: "nao_pago" for pid in pedido_ids}
    for pid in BaixaPedido.objects.filter(pedido_id__in=pedido_ids).values_list("pedido_id", flat=True):
        result[pid] = "pago"
    contagem: dict[int, list[int]] = {}
    for pid, baixada in ParcelaPedido.objects.filter(
        pedido_id__in=pedido_ids
    ).values_list("pedido_id", "baixada"):
        c = contagem.setdefault(pid, [0, 0])
        c[0] += 1
        if baixada:
            c[1] += 1
    for pid, (qtd_total, qtd_ok) in contagem.items():
        if result.get(pid) == "pago":
            continue
        if qtd_total > 0:
            if qtd_ok == qtd_total:
                result[pid] = "pago"
            elif qtd_ok > 0:
                result[pid] = "parcial"
    return result


def linhas_comissao(colaborador, ano: int, mes: int) -> dict:
    inicio, fim = _intervalo_mes(ano, mes)

    # Para capturar baixas do mês anterior que caem neste mês (> 5° DU do mês anterior)
    if mes == 1:
        prev_ano, prev_mes = ano - 1, 12
    else:
        prev_ano, prev_mes = ano, mes - 1
    prev_inicio, _ = _intervalo_mes(prev_ano, prev_mes)

    # Janela de lookback de 12 meses para pedidos antigos com vencimentos no mês atual
    lookback_pedidos = date(ano - 1, mes, 1)

    # Overrides para todo o range estendido
    all_overrides = {
        c.pedido_id: c
        for c in ComissaoPedido.objects.filter(colaborador=colaborador).select_related("pedido")
        if c.pedido.data_pedido >= lookback_pedidos
    }

    # --- Pedidos com data_pedido no período (para linhas normais) ---
    pedidos_periodo: dict[int, PedidoBling] = {}
    if colaborador.bling_vendedor_id:
        for p in PedidoBling.objects.filter(
            vendedor_id=colaborador.bling_vendedor_id,
            situacao_id__in=list(ATENDIDO_COMISSAO_IDS.keys()),
            data_pedido__gte=inicio,
            data_pedido__lte=fim,
        ):
            pedidos_periodo[p.id] = p
    for ov in all_overrides.values():
        if inicio <= ov.pedido.data_pedido <= fim:
            pedidos_periodo[ov.pedido_id] = ov.pedido

    # Parcelas dos pedidos do período
    parcelas_periodo: dict[int, list] = {}
    if pedidos_periodo:
        for parc in ParcelaPedido.objects.filter(
            pedido_id__in=pedidos_periodo.keys()
        ).order_by("numero"):
            parcelas_periodo.setdefault(parc.pedido_id, []).append(parc)

    # --- Pedidos históricos: busca parcelas com data relevante neste período ---
    # (baixa no mês anterior após 5° DU, ou baixa no mês atual, ou vencimento no mês atual)
    parcelas_hist_qs = (
        ParcelaPedido.objects
        .filter(
            pedido__situacao_id__in=list(ATENDIDO_COMISSAO_IDS.keys()),
            pedido__data_pedido__gte=lookback_pedidos,
            pedido__data_pedido__lt=inicio,
        )
        .select_related("pedido")
        .order_by("numero")
    )
    if colaborador.bling_vendedor_id:
        parcelas_hist_qs = parcelas_hist_qs.filter(
            pedido__vendedor_id=colaborador.bling_vendedor_id
        )

    # Overrides de pedidos anteriores ao período
    override_ids_pre = {ov.pedido_id for ov in all_overrides.values() if ov.pedido.data_pedido < inicio}

    pedidos_hist: dict[int, PedidoBling] = {}
    parcelas_hist: dict[int, list] = {}
    seen_parc_ids: set[int] = set()

    for parc in parcelas_hist_qs:
        if parc.id in seen_parc_ids:
            continue
        seen_parc_ids.add(parc.id)
        pid = parc.pedido_id
        pedidos_hist[pid] = parc.pedido
        parcelas_hist.setdefault(pid, []).append(parc)

    if override_ids_pre:
        for parc in (
            ParcelaPedido.objects
            .filter(pedido_id__in=override_ids_pre)
            .select_related("pedido")
            .order_by("numero")
        ):
            if parc.id in seen_parc_ids:
                continue
            seen_parc_ids.add(parc.id)
            pid = parc.pedido_id
            if pid not in pedidos_hist:
                pedidos_hist[pid] = parc.pedido
            parcelas_hist.setdefault(pid, []).append(parc)

    # --- Status de pagamento ---
    all_ids = list(pedidos_periodo.keys()) + list(pedidos_hist.keys())
    pag_status = _pagamento_status(all_ids)

    # Pedidos com BaixaPedido (pagamento integral à vista) → não parcelar comissão
    baixa_ids: set[int] = set(
        BaixaPedido.objects.filter(pedido_id__in=all_ids).values_list("pedido_id", flat=True)
    )

    linhas: list[dict] = []
    total = Decimal("0.00")

    def _calc(p, ov):
        if ov:
            base = ov.base_efetiva()
            pct = ov.percentual_efetivo()
            valida, manual = ov.valida, ov.manual
            valor = (base * pct / Decimal("100")).quantize(Decimal("0.01"))
        elif p.comissao_total_bling is not None and p.comissao_total_bling > Decimal("0"):
            pct = colaborador.comissao_percentual_padrao
            valor = p.comissao_total_bling
            base = (valor / pct * Decimal("100")).quantize(Decimal("0.01")) if pct else p.valor_total
            valida, manual = True, False
        else:
            base = p.valor_total
            pct = colaborador.comissao_percentual_padrao
            valida, manual = True, False
            valor = (base * pct / Decimal("100")).quantize(Decimal("0.01"))
        return base, pct, valor, valida, manual

    def _add_normal_line(p, ov):
        nonlocal total
        base, pct, valor, valida, manual = _calc(p, ov)
        st = pag_status.get(p.id, "nao_pago")
        linhas.append({
            "pedido": p,
            "ano": ano, "mes": mes,
            "data": p.data_pedido,
            "numero": p.numero or p.bling_id,
            "cliente": p.cliente_nome,
            "situacao": p.situacao_nome,
            "base": base,
            "percentual": pct,
            "valor": valor,
            "valida": valida,
            "manual": manual,
            "pago": st == "pago",
            "parcial": st == "parcial",
            "comissao_parcelada": False,
        })
        if valida:
            total += valor

    def _add_split_lines(p, ov, parcelas_list):
        nonlocal total
        base_total, pct, valor_total, valida, manual = _calc(p, ov)
        if not valida:
            return
        valor_pedido = p.valor_total or Decimal("1")
        for i, parc in enumerate(parcelas_list, 1):
            if parc.baixada and parc.data_efetiva:
                comp_ano, comp_mes = _mes_competencia(parc.data_efetiva)
                data_linha = parc.data_efetiva
            elif parc.data_vencimento:
                comp_ano, comp_mes = parc.data_vencimento.year, parc.data_vencimento.month
                data_linha = parc.data_vencimento
            else:
                comp_ano, comp_mes = p.data_pedido.year, p.data_pedido.month
                data_linha = p.data_pedido

            if (comp_ano, comp_mes) != (ano, mes):
                continue

            proporcao = (parc.valor / valor_pedido) if valor_pedido else Decimal("0")
            valor_parc = (valor_total * proporcao).quantize(Decimal("0.01"))

            linhas.append({
                "pedido": p,
                "ano": ano, "mes": mes,
                "data": data_linha,
                "numero": p.numero or p.bling_id,
                "cliente": p.cliente_nome,
                "situacao": p.situacao_nome,
                "base": parc.valor,
                "percentual": pct,
                "valor": valor_parc,
                "valida": valida,
                "manual": manual,
                "pago": parc.baixada,
                "parcial": False,
                "comissao_parcelada": True,
                "parcela_num": i,
                "parcela_total": len(parcelas_list),
            })
            if valida:
                total += valor_parc

    def _deve_parcelar(p, ov, parcelas_list) -> bool:
        _, _, valor, valida, _ = _calc(p, ov)
        return (
            valida
            and valor > COMISSAO_PARCELAMENTO_LIMITE
            and len(parcelas_list) > 1
            and p.id not in baixa_ids  # BaixaPedido = pago integral, não parcelar
        )

    # Pedidos do período
    for p in sorted(pedidos_periodo.values(), key=lambda x: (x.data_pedido, x.numero or "")):
        ov = all_overrides.get(p.id)
        parcelas = parcelas_periodo.get(p.id, [])
        if _deve_parcelar(p, ov, parcelas):
            _add_split_lines(p, ov, parcelas)
        else:
            _add_normal_line(p, ov)

    # Pedidos históricos (apenas split, se tiverem linhas no período atual)
    for p in sorted(pedidos_hist.values(), key=lambda x: (x.data_pedido, x.numero or "")):
        if p.id in pedidos_periodo:
            continue
        ov = all_overrides.get(p.id)
        parcelas = parcelas_hist.get(p.id, [])
        if _deve_parcelar(p, ov, parcelas):
            _add_split_lines(p, ov, parcelas)

    linhas.sort(key=lambda x: (x["data"], str(x["numero"])))
    return {"linhas": linhas, "total": total.quantize(Decimal("0.01"))}


def linhas_comissao_periodo(colaborador, meses: list[tuple[int, int]]) -> dict:
    """Agrega as comissões da vendedora ao longo de vários meses."""
    linhas = []
    total = Decimal("0.00")
    for ano, mes in meses:
        d = linhas_comissao(colaborador, ano, mes)
        linhas.extend(d["linhas"])
        total += d["total"]
    return {"linhas": linhas, "total": total.quantize(Decimal("0.01"))}
