"""Tela do funcionário: corrigir os próprios dias com ponto faltando (propor horários)."""

from datetime import date, time

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import BatidaPonto, CorrecaoPonto, NotificacaoPonto

# (tipo, prefixo, rótulo)
SLOTS = [
    ("entrada", "e", "Entrada"),
    ("saida_almoco", "sa", "Saída p/ almoço"),
    ("volta_almoco", "va", "Volta do almoço"),
    ("saida", "s", "Saída"),
]


def _parse_hora(valor: str) -> time | None:
    try:
        h, m = valor.split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


@perm_required("rh.ponto_bater")
def view_correcoes(request: HttpRequest) -> HttpResponse:
    colaborador = getattr(request.user, "colaborador", None)
    pendencias = []
    if colaborador:
        notifs = (
            NotificacaoPonto.objects.filter(colaborador=colaborador, data__lt=timezone.localdate())
            .exclude(status="resolvido").order_by("data")
        )
        for notif in notifs:
            dia = notif.data
            batidas = {
                b.tipo: timezone.localtime(b.momento).strftime("%H:%M")
                for b in BatidaPonto.objects.filter(colaborador=colaborador, momento__date=dia)
            }
            corr = CorrecaoPonto.objects.filter(colaborador=colaborador, data=dia).first()
            prop = {}
            if corr:
                prop = {
                    "entrada": corr.prop_entrada, "saida_almoco": corr.prop_saida_almoco,
                    "volta_almoco": corr.prop_volta_almoco, "saida": corr.prop_saida,
                }
            slots = []
            for tipo, pref, label in SLOTS:
                valor = ""
                if prop.get(tipo):
                    valor = prop[tipo].strftime("%H:%M")
                elif batidas.get(tipo):
                    valor = batidas[tipo]
                # "sugerido" = já existe uma batida nesse tipo, preenchida como sugestão —
                # o campo continua editável, pois o tipo gravado pode estar errado
                # (dia com só 1 batida vira "entrada" por posição, mesmo sendo a saída).
                slots.append({"pref": pref, "label": label, "hora": valor, "sugerido": tipo in batidas})
            enviada = bool(corr and corr.status == "pendente")
            pendencias.append({
                "data": dia,
                "iso": dia.isoformat(),
                "mensagem": notif.mensagem,
                "enviada": enviada,
                "rejeitada": bool(corr and corr.status == "rejeitada"),
                "slots": slots,
                "sem_almoco": corr.sem_almoco if corr else False,
            })

    return render(request, "rh/correcoes.html", {
        "colaborador": colaborador,
        "pendencias": pendencias,
    })


@perm_required("rh.ponto_bater")
@require_POST
def view_propor_correcao(request: HttpRequest) -> HttpResponse:
    colaborador = getattr(request.user, "colaborador", None)
    if colaborador is None:
        messages.error(request, "Seu usuário não está vinculado a um colaborador.")
        return redirect("rh:correcoes")

    try:
        dia = date.fromisoformat(request.POST.get("data", ""))
    except ValueError:
        messages.error(request, "Dia inválido.")
        return redirect("rh:correcoes")

    sem_almoco = request.POST.get("sem_almoco") == "on"
    e = _parse_hora(request.POST.get("e", ""))
    sa = _parse_hora(request.POST.get("sa", ""))
    va = _parse_hora(request.POST.get("va", ""))
    s = _parse_hora(request.POST.get("s", ""))

    if not e or not s:
        messages.error(request, "Informe ao menos a entrada e a saída.")
        return redirect("rh:correcoes")

    from apps.rh.services.correcoes import horarios_em_ordem
    if not horarios_em_ordem(sem_almoco, e, sa, va, s):
        messages.error(request, "Os horários devem estar em ordem: entrada, saída p/ almoço, volta e saída.")
        return redirect("rh:correcoes")

    motivo = request.POST.get("observacao", "").strip()
    if not motivo:
        messages.error(request, "Informe o motivo da correção.")
        return redirect("rh:correcoes")

    CorrecaoPonto.objects.update_or_create(
        colaborador=colaborador, data=dia,
        defaults={
            "prop_entrada": e,
            "prop_saida_almoco": None if sem_almoco else sa,
            "prop_volta_almoco": None if sem_almoco else va,
            "prop_saida": s,
            "sem_almoco": sem_almoco,
            "observacao": motivo,
            "status": "pendente",
            "avaliado_por": None,
            "avaliado_em": None,
        },
    )
    NotificacaoPonto.objects.filter(colaborador=colaborador, data=dia).update(status="analise", lida=True)
    messages.success(request, f"Correção de {dia:%d/%m} enviada para o gestor aprovar.")
    return redirect("rh:correcoes")
