import logging
from decimal import Decimal, InvalidOperation

import requests

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required

from ..models import MovimentoSaldoLalamove, SolicitacaoEntrega, SolicitacaoEntregaEvento
from ..services import lalamove
from ..services.escopo import qs_do_usuario
from ..services.periodo import PERIODOS, parse_periodo

logger = logging.getLogger("apps.motoqueiro")


@perm_required("motoqueiro.ver_relatorio")
def view_relatorio(request: HttpRequest) -> HttpResponse:
    periodo = parse_periodo(request)

    solicitacoes = list(
        qs_do_usuario(request)
        .filter(criado_em__gte=periodo.inicio, criado_em__lte=periodo.fim)
        .order_by("colaborador__nome", "-criado_em")
    )
    _atualizar_em_andamento(solicitacoes)

    # A linha cancelada continua aparecendo na lista (com o selo "Cancelada"),
    # mas nao entra em quantidade nem em valor — mesma regra do dashboard, em
    # services/escopo.py::qs_contabilizavel.
    secoes_por_colaborador = {}
    for s in solicitacoes:
        secoes_por_colaborador.setdefault(s.colaborador_id, {
            "colaborador": s.colaborador,
            "linhas": [],
            "qtd": 0,
            "total_valor": Decimal("0.00"),
        })
        secao = secoes_por_colaborador[s.colaborador_id]
        secao["linhas"].append(s)
        if s.status != SolicitacaoEntrega.STATUS_CANCELADO:
            secao["qtd"] += 1
            secao["total_valor"] += s.valor

    secoes = sorted(secoes_por_colaborador.values(), key=lambda d: d["colaborador"].nome)

    ctx = {
        "secoes": secoes,
        "periodo": periodo,
        "periodos": PERIODOS,
        "total_geral": sum((s["total_valor"] for s in secoes), Decimal("0.00")),
        "total_corridas": sum(s["qtd"] for s in secoes),
        "status_choices": SolicitacaoEntrega.STATUS_CHOICES,
        "ve_todos": request.user.pode_ver_todas_motoqueiro,
        # Quem pode pedir corrida pode cancelar a que pediu — o escopo de
        # qual corrida ele alcanca ja vem do qs_do_usuario na view.
        "pode_cancelar_corrida": request.user.pode_solicitar_motoqueiro,
        "saldo_lalamove": MovimentoSaldoLalamove.saldo_atual(),
    }
    return render(request, "motoqueiro/relatorio.html", ctx)


@perm_required("motoqueiro.editar_status")
@require_POST
def view_atualizar_status_manual(request: HttpRequest, pk: int) -> HttpResponse:
    """Correção manual de status — para quando o webhook falhar ou a corrida
    não tiver sido criada via API (registro avulso)."""
    solicitacao = get_object_or_404(SolicitacaoEntrega, pk=pk)
    novo_status = request.POST.get("status", "")
    validos = dict(SolicitacaoEntrega.STATUS_CHOICES)
    if novo_status not in validos:
        messages.error(request, "Status inválido.")
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    status_anterior = solicitacao.status
    solicitacao.status = novo_status
    if novo_status in SolicitacaoEntrega.STATUS_FINAIS and not solicitacao.concluido_em:
        solicitacao.concluido_em = timezone.now()
    solicitacao.save(update_fields=["status", "concluido_em", "atualizado_em"])

    SolicitacaoEntregaEvento.objects.create(
        solicitacao=solicitacao,
        status_anterior=status_anterior,
        status_novo=novo_status,
        origem="manual",
        payload={"usuario": request.user.username},
    )
    messages.success(request, f"Status atualizado para \"{validos[novo_status]}\".")
    return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))


@perm_required("motoqueiro.solicitar")
@require_POST
def view_cancelar(request: HttpRequest, pk: int) -> HttpResponse:
    """Cancela a corrida na Lalamove a pedido de quem solicitou.

    O escopo vem do `qs_do_usuario`: quem nao tem `ver_todos` so alcanca as
    proprias corridas, entao ninguem cancela a corrida de outra pessoa por
    engano (nem trocando o pk na URL).

    A janela de cancelamento e' curta e quem decide e' a Lalamove (409
    ERR_CANCELLATION_FORBIDDEN depois que o motoboy ja esta a caminho ha mais
    de 5 min). So mexemos no registro local depois que a API confirmar — nada
    de marcar como cancelada uma corrida que o motoboy ainda vai fazer.
    """
    solicitacao = get_object_or_404(qs_do_usuario(request), pk=pk)

    if not solicitacao.pode_cancelar:
        messages.error(
            request,
            "Esta corrida não pode mais ser cancelada pelo painel "
            f"(status atual: {solicitacao.get_status_display()}).",
        )
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    try:
        lalamove.cancelar_pedido(solicitacao.lalamove_order_id)
    except lalamove.LalamoveError as exc:
        if exc.status_code == 409:
            # ERR_CANCELLATION_FORBIDDEN: a corrida ja passou da janela. Nesse
            # caso o status local quase sempre esta atrasado (foi por isso que
            # o botao apareceu), entao vale reconsultar a Lalamove pra tela
            # parar de mostrar "Aguardando Coleta" numa corrida que ja saiu.
            atual = _ressincronizar_status(solicitacao)
            messages.error(
                request,
                "A Lalamove não aceitou o cancelamento: a corrida já passou do prazo "
                f"de cancelar (situação agora: {atual}). Para cancelar assim mesmo, "
                "fale direto com o suporte da Lalamove pelo aplicativo.",
            )
        else:
            logger.warning("motoqueiro cancelar: falha na Lalamove (%s): %s", exc.status_code, exc.body)
            messages.error(request, f"Não foi possível cancelar na Lalamove (erro {exc.status_code}). Tente de novo.")
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))
    except requests.RequestException as exc:
        # Timeout / conexao caida com a Lalamove. Sem isso a excecao subia e a
        # pessoa levava uma tela de erro 500 em cima de uma corrida que
        # continua valendo — pior momento possivel pra um erro cru.
        logger.warning("motoqueiro cancelar: nao deu pra falar com a Lalamove: %s", exc)
        messages.error(
            request,
            "Não conseguimos falar com a Lalamove agora, então a corrida NÃO foi "
            "cancelada. Tente de novo em alguns segundos; se continuar, cancele "
            "pelo aplicativo da Lalamove.",
        )
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    status_anterior = solicitacao.status
    solicitacao.status = SolicitacaoEntrega.STATUS_CANCELADO
    solicitacao.lalamove_status_raw = "CANCELED"
    solicitacao.concluido_em = timezone.now()
    solicitacao.save(update_fields=["status", "lalamove_status_raw", "concluido_em", "atualizado_em"])

    SolicitacaoEntregaEvento.objects.create(
        solicitacao=solicitacao,
        status_anterior=status_anterior,
        status_novo=solicitacao.status,
        status_raw="CANCELED",
        origem="cancelamento",
        payload={"usuario": request.user.username},
    )

    # Estorno no ledger: a confirmacao da corrida lancou um debito automatico,
    # e cancelamento antes do motoboy sair nao e' cobrado pela Lalamove. O
    # ledger e' append-only (nunca se apaga o debito), entao o acerto e' um
    # credito de mesmo valor. Se a Lalamove cobrar taxa em algum caso, o
    # superadmin lanca o debito da taxa na tela de Saldo.
    MovimentoSaldoLalamove.objects.create(
        tipo=MovimentoSaldoLalamove.TIPO_CREDITO,
        origem=MovimentoSaldoLalamove.ORIGEM_CORRIDA,
        valor=solicitacao.valor,
        descricao=f"Estorno — corrida #{solicitacao.id} cancelada por {request.user.username}",
        solicitacao=solicitacao,
        lancado_por=request.user,
    )

    messages.success(request, f"Corrida #{solicitacao.id} cancelada na Lalamove e valor estornado no saldo.")
    return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))


def _ressincronizar_status(solicitacao: SolicitacaoEntrega, timeout: int | None = None) -> str:
    """Reconsulta o status real na Lalamove e grava se tiver mudado.

    Duas situacoes usam isto: a recusa de cancelamento (se a Lalamove diz que
    passou do prazo, o status local esta velho) e o refresh da listagem do
    relatorio. Nos dois casos a causa e a mesma — webhook que nao chegou.
    Devolve o rotulo do status atual. Nunca levanta excecao: e' conforto de
    tela, nao pode virar um segundo erro em cima do primeiro.
    """
    try:
        dados = lalamove.obter_pedido(solicitacao.lalamove_order_id, timeout=timeout).get("data", {})
        status_raw = dados.get("status", "")
        if not status_raw:
            return solicitacao.get_status_display()
        status_novo = lalamove.traduzir_status(status_raw)
        if status_novo != solicitacao.status:
            status_anterior = solicitacao.status
            solicitacao.status = status_novo
            solicitacao.lalamove_status_raw = status_raw
            if status_novo in SolicitacaoEntrega.STATUS_FINAIS and not solicitacao.concluido_em:
                solicitacao.concluido_em = timezone.now()
            solicitacao.save(update_fields=["status", "lalamove_status_raw", "concluido_em", "atualizado_em"])
            SolicitacaoEntregaEvento.objects.create(
                solicitacao=solicitacao,
                status_anterior=status_anterior,
                status_novo=status_novo,
                status_raw=status_raw,
                origem="polling",
                payload={"motivo": "recusa de cancelamento"},
            )
        return solicitacao.get_status_display()
    except (lalamove.LalamoveError, requests.RequestException) as exc:
        logger.warning("motoqueiro cancelar: falhou ao reconsultar status: %s", exc)
        return solicitacao.get_status_display()



@perm_required("motoqueiro.solicitar")
@require_POST
def view_priorizar(request: HttpRequest, pk: int) -> HttpResponse:
    """Sobe a taxa de prioridade da corrida um degrau (R$ 3 -> 5 -> 10).

    Na Lalamove a prioridade nao acumula: o valor novo substitui o anterior.
    Entao subir de R$ 3 pra R$ 5 deixa a corrida custando R$ 5 a mais, nao
    R$ 8 — e o ledger recebe so a DIFERENCA, senao o saldo passaria a mentir.

    O clique duplo e' barrado comparando o valor pedido com
    `proxima_prioridade`: se o primeiro clique ja aplicou R$ 3, um segundo
    POST de R$ 3 nao bate mais com o proximo degrau e e' recusado sem chamar
    a API.
    """
    solicitacao = get_object_or_404(qs_do_usuario(request), pk=pk)

    if not solicitacao.pode_priorizar:
        if solicitacao.proxima_prioridade is None:
            messages.error(request, "Esta corrida já está na prioridade máxima de R$ 10,00.")
        else:
            messages.error(
                request,
                "Não dá mais para aumentar a prioridade desta corrida "
                f"(situação atual: {solicitacao.get_status_display()}).",
            )
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    try:
        pedido = Decimal(request.POST.get("valor", ""))
    except (InvalidOperation, TypeError):
        messages.error(request, "Valor de prioridade inválido.")
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    proxima = solicitacao.proxima_prioridade
    if pedido != proxima:
        # Clique duplo, ou tela velha: o degrau ja mudou desde que a pagina
        # carregou. Nao chama a API e explica onde a prioridade esta.
        messages.error(
            request,
            f"A prioridade desta corrida já está em R$ {solicitacao.lalamove_prioridade:.2f}"
            .replace(".", ",")
            + f". O próximo passo seria R$ {proxima:.2f}.".replace(".", ","),
        )
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    try:
        lalamove.adicionar_prioridade(solicitacao.lalamove_order_id, proxima)
    except lalamove.LalamoveError as exc:
        logger.warning("motoqueiro prioridade: recusada pela Lalamove (%s): %s", exc.status_code, exc.body)
        if "TIPS" in (exc.body or ""):
            messages.error(request, "A Lalamove não aceitou esse valor de prioridade para esta região.")
        else:
            atual = _ressincronizar_status(solicitacao)
            messages.error(
                request,
                "A Lalamove não aceitou aumentar a prioridade — normalmente porque um "
                f"motoboy já aceitou a corrida (situação agora: {atual}).",
            )
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))
    except requests.RequestException as exc:
        logger.warning("motoqueiro prioridade: nao deu pra falar com a Lalamove: %s", exc)
        messages.error(
            request,
            "Não conseguimos falar com a Lalamove agora, então a prioridade NÃO foi "
            "alterada. Tente de novo em alguns segundos.",
        )
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    anterior = solicitacao.lalamove_prioridade
    diferenca = proxima - anterior
    solicitacao.lalamove_prioridade = proxima
    solicitacao.valor = solicitacao.valor + diferenca
    solicitacao.save(update_fields=["lalamove_prioridade", "valor", "atualizado_em"])

    MovimentoSaldoLalamove.objects.create(
        tipo=MovimentoSaldoLalamove.TIPO_DEBITO,
        origem=MovimentoSaldoLalamove.ORIGEM_CORRIDA,
        valor=diferenca,
        descricao=(
            f"Prioridade da corrida #{solicitacao.id}: "
            f"R$ {anterior:.2f} para R$ {proxima:.2f} (por {request.user.username})"
        ).replace(".", ","),
        solicitacao=solicitacao,
        lancado_por=request.user,
    )

    messages.success(
        request,
        f"Prioridade da corrida #{solicitacao.id} aumentada para R$ {proxima:.2f}.".replace(".", ","),
    )
    return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

# Quantas corridas em andamento o relatorio reconsulta por carregamento. Sao
# chamadas sincronas dentro do request; o teto evita que um dia com muitas
# corridas abertas transforme a pagina numa fila de chamadas de API.
MAX_REFRESH_POR_CARGA = 8
# Nao reconsulta a mesma corrida a cada F5 — so se o registro local nao foi
# tocado no ultimo minuto.
IDADE_MINIMA_REFRESH = 60


def _atualizar_em_andamento(solicitacoes: list[SolicitacaoEntrega]) -> None:
    """Reconsulta na Lalamove o status das corridas que ainda estao rolando.

    O webhook e o caminho de tempo real, mas ele falha calado (URL errada no
    portal, notificacao perdida) e ai a tela fica dizendo "Aguardando Coleta"
    numa corrida que ja achou motoboy — foi o que quase fez pedirem a mesma
    corrida duas vezes. Este refresh e a rede de seguranca: enquanto alguem
    esta olhando o relatorio, o painel se corrige sozinho.

    Timeout curto e teto de chamadas de proposito: se a Lalamove estiver lenta,
    a linha fica com o status velho e a pagina abre do mesmo jeito.
    """
    agora = timezone.now()
    pendentes = [
        s for s in solicitacoes
        if s.lalamove_order_id
        and not s.eh_status_final
        and (agora - s.atualizado_em).total_seconds() > IDADE_MINIMA_REFRESH
    ]
    for solicitacao in pendentes[:MAX_REFRESH_POR_CARGA]:
        _ressincronizar_status(solicitacao, timeout=6)
