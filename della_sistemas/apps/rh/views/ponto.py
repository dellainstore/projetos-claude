from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from datetime import timedelta

from apps.core.decorators import perm_required
from apps.rh.models import (
    BatidaPonto,
    Colaborador,
    LocalEmpresa,
    NotificacaoPonto,
    ParametrosPonto,
)
from apps.rh.services.ponto import (
    banco_de_horas,
    proximo_tipo,
    reordenar_tipos_do_dia,
    validar_geofence,
)
from apps.rh.services.utils import parse_int


def _meu_colaborador(request):
    return getattr(request.user, "colaborador", None)


def _contexto_app(colaborador, hoje):
    batidas_hoje = list(
        BatidaPonto.objects.filter(colaborador=colaborador, momento__date=hoje).order_by("momento")
    )
    prox = proximo_tipo(colaborador, hoje)
    return {
        "colaborador": colaborador,
        "batidas_hoje": batidas_hoje,
        "proximo_tipo": prox,
        "proximo_label": dict(BatidaPonto.TIPO_CHOICES).get(prox) if prox else None,
        "dia_completo": prox is None,
    }


@perm_required("rh.ponto_bater")
def view_ponto(request: HttpRequest) -> HttpResponse:
    colaborador = _meu_colaborador(request)
    hoje = timezone.localdate()
    ctx = {"colaborador": colaborador, "local_ok": LocalEmpresa.objects.filter(ativo=True).exists()}
    if colaborador:
        ctx.update(_contexto_app(colaborador, hoje))
        ctx["qtd_pendencias"] = (
            NotificacaoPonto.objects.filter(colaborador=colaborador, data__lt=hoje)
            .exclude(status="resolvido").count()
        )
    return render(request, "rh/ponto.html", ctx)


@perm_required("rh.ponto_bater")
@require_POST
def view_bater(request: HttpRequest) -> HttpResponse:
    colaborador = _meu_colaborador(request)
    if colaborador is None:
        return render(request, "rh/_ponto_resultado.html", {
            "erro": "Seu usuário não está vinculado a um colaborador. Avise o gestor.",
        })

    hoje = timezone.localdate()
    agora = timezone.now()
    tipo = proximo_tipo(colaborador, hoje)
    if tipo is None:
        ctx = _contexto_app(colaborador, hoje)
        ctx["erro"] = "Você já registrou as 4 batidas de hoje."
        return render(request, "rh/_ponto_app.html", ctx)

    # Anti-clique-duplo: bloqueia uma 2ª batida muito próxima da anterior.
    intervalo = ParametrosPonto.get().intervalo_minimo_minutos
    ultima = (
        BatidaPonto.objects.filter(colaborador=colaborador, momento__date=hoje)
        .order_by("-momento").first()
    )
    if ultima and intervalo > 0 and agora - ultima.momento < timedelta(minutes=intervalo):
        ctx = _contexto_app(colaborador, hoje)
        ctx["erro"] = (f"Você acabou de bater o ponto às {timezone.localtime(ultima.momento):%H:%M}. "
                       f"Aguarde {intervalo} min para a próxima batida.")
        return render(request, "rh/_ponto_app.html", ctx)

    try:
        lat = float(request.POST.get("latitude"))
        lon = float(request.POST.get("longitude"))
    except (TypeError, ValueError):
        ctx = _contexto_app(colaborador, hoje)
        ctx["erro"] = "Não foi possível obter sua localização. Ative o GPS e tente novamente."
        return render(request, "rh/_ponto_app.html", ctx)

    dentro, dist, loja = validar_geofence(colaborador, lat, lon)
    if loja is None:
        ctx = _contexto_app(colaborador, hoje)
        ctx["erro"] = "Nenhuma loja configurada/vinculada para o seu ponto. Avise o gestor."
        return render(request, "rh/_ponto_app.html", ctx)
    if not dentro:
        ctx = _contexto_app(colaborador, hoje)
        ctx["erro"] = ("Você está fora do local permitido para a batida do ponto. "
                       "Aproxime-se e tente novamente.")
        return render(request, "rh/_ponto_app.html", ctx)

    BatidaPonto.objects.create(
        colaborador=colaborador,
        momento=timezone.now(),
        tipo=tipo,
        loja=loja,
        latitude=Decimal(str(lat)),
        longitude=Decimal(str(lon)),
        distancia_m=Decimal(str(round(dist, 2))),
        dentro_raio=True,
        origem="app",
    )
    reordenar_tipos_do_dia(colaborador, hoje)
    ctx = _contexto_app(colaborador, hoje)
    ctx["sucesso"] = "Ponto registrado!"
    return render(request, "rh/_ponto_app.html", ctx)


@perm_required("rh.ponto_gerir")
def view_relatorio(request: HttpRequest) -> HttpResponse:
    hoje = date.today()
    from apps.rh.services.utils import competencia_opcoes, parse_competencia
    inicio_controle = ParametrosPonto.get().data_inicio
    ano, mes = parse_competencia(request, hoje)
    if date(ano, mes, 1) < inicio_controle:
        ano, mes = inicio_controle.year, inicio_controle.month

    import calendar
    from apps.metas.services.relatorio import MESES_PT
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])

    colaboradores = list(Colaborador.objects.filter(ativo=True).order_by("nome"))
    relatorios = []
    for c in colaboradores:
        dados = banco_de_horas(c, inicio, fim)
        # banco_de_horas() agora inclui todo dia do período (pro espelho em PDF
        # listar sábado/domingo/feriado/atestado). Aqui, no resumo mensal por
        # colaborador, isso só interessa quando há algo pra ver — mantém o
        # comportamento enxuto de antes, escondendo o dia de folga "vazio" (sem
        # batida, sem saldo, sem afastamento/feriado) que não muda em nada.
        dias_relevantes = [
            d for d in dados["dias"]
            if d["batidas"] or d["saldo"] or d["afastamento"] or d["feriado"] or d["sem_registro"]
        ]
        relatorios.append({"colaborador": c, "dias": dias_relevantes, "saldo_total": dados["saldo_total"]})

    return render(request, "rh/ponto_relatorio.html", {
        "relatorios": relatorios,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "meses_opcoes": competencia_opcoes(hoje, desde=inicio_controle),
    })
