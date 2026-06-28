"""Sincronização de pedidos do Bling com o banco local."""

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from apps.pedidos.models import BaixaPedido, HistoricoDataPedido, HistoricoSituacaoPedido, ParcelaPedido, PedidoBling
from apps.pedidos.services.bling_client import listar_todos_pedidos, obter_detalhe_pedido
from apps.pedidos.services.formas_pagamento import FORMAS_PAGAMENTO
from apps.pedidos.services.situacoes import ALL_IDS, ATENDIDO_IDS

logger = logging.getLogger(__name__)


def _parse_date(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(valor).date()
    except (ValueError, TypeError):
        try:
            return date.fromisoformat(str(valor)[:10])
        except (ValueError, TypeError):
            return None


def _extrair_forma_pagamento(detalhe: dict) -> str:
    """Retorna nome da forma de pagamento a partir das parcelas do detalhe do pedido."""
    parcelas: list = detalhe.get("parcelas") or []
    if not parcelas:
        return ""
    primeira = parcelas[0]
    forma: dict = primeira.get("formaPagamento") or {}
    forma_id = forma.get("id")
    if forma_id:
        nome = FORMAS_PAGAMENTO.get(forma_id)
        if nome:
            return nome
    # Fallback: só a quantidade de parcelas
    qtd = len(parcelas)
    return f"{qtd}x" if qtd > 1 else "1x"


def _extrair_data_pagamento(detalhe: dict) -> date | None:
    """Retorna a data da primeira parcela do pedido."""
    parcelas: list = detalhe.get("parcelas") or []
    if not parcelas:
        return None
    primeira = parcelas[0]
    raw = primeira.get("dataVencimento") or primeira.get("data") or primeira.get("vencimento")
    return _parse_date(raw)


INICIO_2026 = date(2026, 1, 1)


def _sync_parcelas(pedido: PedidoBling, parcelas_raw: list) -> None:
    """Faz upsert das parcelas do Bling preservando status de baixada."""
    if not parcelas_raw:
        return
    existing_map = {p.numero: p for p in pedido.parcelas.all()}
    for i, parc in enumerate(parcelas_raw, 1):
        forma: dict = parc.get("formaPagamento") or {}
        forma_id = forma.get("id")
        forma_nome = FORMAS_PAGAMENTO.get(forma_id, "") if forma_id else ""
        try:
            valor = Decimal(str(parc.get("valor") or 0))
        except InvalidOperation:
            valor = Decimal("0")
        raw_date = parc.get("dataVencimento") or parc.get("data") or parc.get("vencimento")
        data_venc = _parse_date(raw_date)
        if i in existing_map:
            p = existing_map[i]
            p.valor = valor
            p.data_vencimento = data_venc
            p.forma_pagamento = forma_nome
            p.forma_pagamento_id = forma_id
            p.save(update_fields=["valor", "data_vencimento", "forma_pagamento", "forma_pagamento_id"])
        else:
            ParcelaPedido.objects.create(
                pedido=pedido,
                numero=i,
                valor=valor,
                data_vencimento=data_venc,
                forma_pagamento=forma_nome,
                forma_pagamento_id=forma_id,
            )


def sync_pedidos(
    situacao_ids: list[int] | None = None,
    dias_retroativos: int | None = None,
    on_progress=None,
) -> dict[str, int]:
    """Busca pedidos do Bling e faz upsert no banco local.

    Busca TODOS os pedidos por período sem filtrar por situação, capturando
    qualquer mudança de status independente do ID mapeado em ALL_IDS.
    on_progress(pct: int, msg: str) é chamado a cada página buscada.
    Retorna dict com contagens: inserted, updated, unchanged, errors.
    """
    hoje = date.today()
    if dias_retroativos is not None:
        data_ini = (hoje - timedelta(days=dias_retroativos)).isoformat()
    else:
        data_ini = INICIO_2026.isoformat()
    data_fim = hoje.isoformat()

    stats: dict[str, int] = {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}

    def _on_page(pagina: int) -> None:
        if on_progress:
            on_progress(min(85, pagina * 8), f"Buscando pedidos — página {pagina}…")

    todos_pedidos = listar_todos_pedidos(data_ini, data_fim, on_page=_on_page)
    logger.info("Sync: %d pedidos encontrados no período", len(todos_pedidos))

    if on_progress:
        on_progress(88, f"{len(todos_pedidos)} pedidos encontrados. Processando…")

    for p in todos_pedidos:
        try:
            bling_id: int = p.get("id")
            if not bling_id:
                continue

            situacao_raw: dict = p.get("situacao") or {}
            situacao_id: int = situacao_raw.get("id") or 0
            # Nome real do Bling tem prioridade; fallback para mapeamento local ou genérico
            situacao_nome = situacao_raw.get("nome") or ALL_IDS.get(situacao_id) or f"Situação não encontrada (ID:{situacao_id})"

            data_pedido = _parse_date(p.get("data"))
            if data_pedido is None:
                data_pedido = date.today()

            try:
                valor_total = Decimal(str(p.get("total") or 0))
            except InvalidOperation:
                valor_total = Decimal("0")

            contato: dict = p.get("contato") or {}
            cliente_nome = contato.get("nome") or ""
            numero = str(p.get("numero") or "")

            # Auto-marca permuta pelo nome real retornado pelo Bling
            is_permuta = "permuta" in situacao_nome.lower()

            existing = PedidoBling.objects.filter(bling_id=bling_id).first()

            # O detalhe do pedido custa 1 chamada EXTRA à API por pedido. Para
            # acelerar o sync, só buscamos quando realmente há o que atualizar:
            # pedido atendido que é novo, mudou de situação, teve valor/data
            # alterados ou ainda não tem parcelas salvas. Atendido inalterado é
            # pulado — sem chamada à API.
            forma_pagamento = ""
            data_pagamento: date | None = None
            parcelas_raw: list = []
            if situacao_id in ATENDIDO_IDS:
                precisa_detalhe = (
                    existing is None
                    or existing.situacao_id != situacao_id
                    or existing.valor_total != valor_total
                    or existing.data_pedido != data_pedido
                    or not existing.parcelas.exists()
                )
                if precisa_detalhe:
                    detalhe = obter_detalhe_pedido(bling_id)
                    forma_pagamento = _extrair_forma_pagamento(detalhe)
                    data_pagamento = _extrair_data_pagamento(detalhe)
                    parcelas_raw = detalhe.get("parcelas") or []

            if existing:
                changed = existing.situacao_id != situacao_id
                if changed:
                    HistoricoSituacaoPedido.objects.create(
                        pedido=existing,
                        situacao_id=situacao_id,
                        situacao_nome=situacao_nome,
                        situacao_anterior_id=existing.situacao_id,
                        situacao_anterior_nome=existing.situacao_nome,
                    )

                data_mudou = existing.data_pedido != data_pedido
                if data_mudou:
                    HistoricoDataPedido.objects.create(
                        pedido=existing,
                        data_anterior=existing.data_pedido,
                        data_nova=data_pedido,
                    )

                existing.situacao_id   = situacao_id
                existing.situacao_nome = situacao_nome
                existing.data_pedido   = data_pedido
                existing.valor_total   = valor_total
                existing.cliente_nome  = cliente_nome
                if numero:
                    existing.numero = numero
                if forma_pagamento:
                    existing.forma_pagamento = forma_pagamento
                if data_pagamento:
                    existing.data_pagamento = data_pagamento
                if is_permuta:
                    existing.is_permuta = True
                existing.save()
                if parcelas_raw:
                    _sync_parcelas(existing, parcelas_raw)
                stats["updated" if (changed or data_mudou) else "unchanged"] += 1
            else:
                obj = PedidoBling.objects.create(
                    bling_id=bling_id,
                    numero=numero,
                    data_pedido=data_pedido,
                    cliente_nome=cliente_nome,
                    valor_total=valor_total,
                    situacao_id=situacao_id,
                    situacao_nome=situacao_nome,
                    forma_pagamento=forma_pagamento,
                    data_pagamento=data_pagamento,
                    is_permuta=is_permuta,
                )
                HistoricoSituacaoPedido.objects.create(
                    pedido=obj,
                    situacao_id=situacao_id,
                    situacao_nome=situacao_nome,
                )
                if parcelas_raw:
                    _sync_parcelas(obj, parcelas_raw)
                stats["inserted"] += 1

        except Exception as exc:
            logger.error("Erro ao sincronizar pedido %s: %s", p.get("id"), exc, exc_info=True)
            stats["errors"] += 1

    if on_progress:
        on_progress(100, "Concluído")

    return stats
