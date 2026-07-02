"""Gestor: aprovar/alterar/rejeitar as correções de ponto propostas pelos funcionários."""

from datetime import time

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import BatidaPonto, CorrecaoPonto
from apps.rh.services.correcoes import aplicar_correcao


def _parse_hora(valor: str) -> time | None:
    try:
        h, m = valor.split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


# (tipo, prefixo, rótulo, atributo do horário proposto)
_SLOTS = [
    ("entrada", "e", "Entrada", "prop_entrada"),
    ("saida_almoco", "sa", "Saída almoço", "prop_saida_almoco"),
    ("volta_almoco", "va", "Volta almoço", "prop_volta_almoco"),
    ("saida", "s", "Saída", "prop_saida"),
]
_LABEL_POR_TIPO = {tipo: label for tipo, _pref, label, _attr in _SLOTS}


@perm_required("rh.ponto_gerir")
def view_aprovacoes(request: HttpRequest) -> HttpResponse:
    pendentes = list(
        CorrecaoPonto.objects.select_related("colaborador")
        .filter(status="pendente").order_by("data")
    )
    avaliadas = list(
        CorrecaoPonto.objects.select_related("colaborador", "avaliado_por")
        .exclude(status="pendente").order_by("-avaliado_em")[:30]
    )
    # Monta os campos: os já batidos ficam travados (alterar só na Jornada);
    # o gestor preenche/ajusta apenas os que faltaram.
    for corr in pendentes:
        atuais = {
            b.tipo: timezone.localtime(b.momento).strftime("%H:%M")
            for b in BatidaPonto.objects.filter(colaborador=corr.colaborador, momento__date=corr.data)
        }
        slots = []
        for tipo, pref, label, attr in _SLOTS:
            prop = getattr(corr, attr)
            valor = prop.strftime("%H:%M") if prop else atuais.get(tipo, "")
            slots.append({
                "pref": pref, "label": label, "hora": valor,
                "travado": tipo in atuais,
                "almoco": tipo in ("saida_almoco", "volta_almoco"),
            })
        corr.slots = slots
    for corr in avaliadas:
        tipos = [t for t in corr.campos_aplicados.split(",") if t]
        corr.aplicados_labels = [_LABEL_POR_TIPO.get(t, t) for t in tipos]
    return render(request, "rh/aprovacoes.html", {
        "pendentes": pendentes,
        "avaliadas": avaliadas,
        "pode_excluir": request.user.is_superadmin,
    })


@perm_required("rh.ponto_gerir")
@require_POST
def view_correcao_aprovar(request: HttpRequest, pk: int) -> HttpResponse:
    corr = get_object_or_404(CorrecaoPonto, pk=pk)
    # O gestor pode ajustar os horários antes de aprovar.
    sem_almoco = request.POST.get("sem_almoco") == "on"
    e = _parse_hora(request.POST.get("e", ""))
    sa = _parse_hora(request.POST.get("sa", ""))
    va = _parse_hora(request.POST.get("va", ""))
    s = _parse_hora(request.POST.get("s", ""))
    if not e or not s:
        messages.error(request, "Informe ao menos a entrada e a saída.")
        return redirect("rh:aprovacoes")

    corr.prop_entrada = e
    corr.prop_saida_almoco = None if sem_almoco else sa
    corr.prop_volta_almoco = None if sem_almoco else va
    corr.prop_saida = s
    corr.sem_almoco = sem_almoco
    corr.save(update_fields=["prop_entrada", "prop_saida_almoco", "prop_volta_almoco", "prop_saida", "sem_almoco"])

    aplicar_correcao(corr, request.user)
    extra = " (sem almoço — 1h a mais)" if sem_almoco else ""
    messages.success(request, f"Correção de {corr.colaborador.nome} ({corr.data:%d/%m}) aprovada{extra}.")
    return redirect("rh:aprovacoes")


@perm_required("rh.ponto_gerir")
@require_POST
def view_correcao_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove uma correção do histórico — apenas super admin."""
    if not request.user.is_superadmin:
        messages.error(request, "Apenas o super admin pode excluir do histórico.")
        return redirect("rh:aprovacoes")
    get_object_or_404(CorrecaoPonto, pk=pk).delete()
    messages.success(request, "Correção removida do histórico.")
    return redirect("rh:aprovacoes")


@perm_required("rh.ponto_gerir")
@require_POST
def view_correcao_rejeitar(request: HttpRequest, pk: int) -> HttpResponse:
    corr = get_object_or_404(CorrecaoPonto, pk=pk)
    corr.status = "rejeitada"
    corr.avaliado_por = request.user
    corr.avaliado_em = timezone.now()
    corr.save(update_fields=["status", "avaliado_por", "avaliado_em"])
    messages.success(request, f"Correção de {corr.colaborador.nome} ({corr.data:%d/%m}) rejeitada. Ajuste manual na Jornada.")
    return redirect("rh:aprovacoes")
