from django.http import HttpRequest

from apps.motoqueiro.models import SolicitacaoEntrega


def qs_do_usuario(request: HttpRequest):
    """Escopo de visibilidade: quem tem `ver_todos` (gestor/superadmin) enxerga
    todo mundo; o restante só enxerga as próprias corridas (pelo colaborador
    vinculado ao próprio login)."""
    qs = SolicitacaoEntrega.objects.select_related("colaborador")
    if request.user.pode_ver_todas_motoqueiro:
        return qs
    colaborador = getattr(request.user, "colaborador", None)
    if not colaborador:
        return qs.none()
    return qs.filter(colaborador=colaborador)


def qs_contabilizavel(request: HttpRequest):
    """Corridas que contam como gasto — ou seja, tudo menos as canceladas.

    REGRA UNICA de numero/valor do modulo: dashboard (cards, rankings,
    grafico) e os totais do relatorio passam por aqui. Corrida cancelada nao
    e' cobrada pela Lalamove (o cancelamento so e' aceito antes do motoboy
    sair) e ja e' estornada no ledger de saldo — deixar ela somando inflaria
    gasto e ranking de funcionaria com corrida que nunca aconteceu.

    Corrida em andamento (aguardando coleta / no percurso) CONTA: o gasto ja
    esta comprometido no momento em que a corrida e confirmada, nao so quando
    a entrega termina.

    A LISTAGEM do relatorio nao usa este filtro de proposito — a linha
    cancelada continua visivel, com o selo "Cancelada", pra ficar claro o que
    aconteceu. O que sai das contas e o numero, nao o registro.
    """
    return qs_do_usuario(request).exclude(status=SolicitacaoEntrega.STATUS_CANCELADO)
