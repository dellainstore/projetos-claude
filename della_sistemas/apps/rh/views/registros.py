"""Registros de ponto: auditoria de batidas por origem (app vs manual do gestor)."""

from datetime import date, timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import AbonoPonto, BatidaPonto, Colaborador
from apps.rh.services.utils import parse_int


@perm_required("rh.ponto_gerir")
def view_registros(request: HttpRequest) -> HttpResponse:
    hoje = timezone.localdate()
    colaboradores = list(Colaborador.objects.filter(ativo=True).order_by("nome"))

    f_colab = parse_int(request.GET.get("colaborador"), 0)
    origem = request.GET.get("origem", "todos")   # todos | app | manual
    periodo = request.GET.get("periodo", "30")     # 7 | 30 | custom

    qs = BatidaPonto.objects.select_related("colaborador", "loja", "ajustado_por").all()
    if f_colab:
        qs = qs.filter(colaborador_id=f_colab)
    if origem in ("app", "manual"):
        qs = qs.filter(origem=origem)

    inicio = fim = None
    if periodo == "7":
        inicio = hoje - timedelta(days=7)
    elif periodo == "30":
        inicio = hoje - timedelta(days=30)
    elif periodo == "custom":
        try:
            inicio = date.fromisoformat(request.GET.get("inicio", ""))
            fim = date.fromisoformat(request.GET.get("fim", ""))
        except ValueError:
            inicio = fim = None
    if inicio:
        qs = qs.filter(momento__date__gte=inicio)
    if fim:
        qs = qs.filter(momento__date__lte=fim)

    batidas = list(qs.order_by("-momento")[:300])

    abonos_qs = AbonoPonto.objects.select_related("colaborador", "abonado_por").all()
    if f_colab:
        abonos_qs = abonos_qs.filter(colaborador_id=f_colab)
    if inicio:
        abonos_qs = abonos_qs.filter(data__gte=inicio)
    if fim:
        abonos_qs = abonos_qs.filter(data__lte=fim)
    abonos = list(abonos_qs.order_by("-data")[:300])

    return render(request, "rh/registros.html", {
        "pode_excluir": request.user.is_superadmin,
        "colaboradores": colaboradores,
        "batidas": batidas,
        "abonos": abonos,
        "f_colab": f_colab,
        "origem": origem,
        "periodo": periodo,
        "inicio": request.GET.get("inicio", ""),
        "fim": request.GET.get("fim", ""),
        "total_app": sum(1 for b in batidas if b.origem == "app"),
        "total_manual": sum(1 for b in batidas if b.origem == "manual"),
    })


@perm_required("rh.ponto_gerir")
@require_POST
def view_registro_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    """Exclui uma batida do histórico — apenas super admin."""
    if not request.user.is_superadmin:
        messages.error(request, "Apenas o super admin pode excluir registros.")
        return redirect("rh:registros")
    b = get_object_or_404(BatidaPonto, pk=pk)
    colaborador, dia = b.colaborador, timezone.localtime(b.momento).date()
    b.delete()
    from apps.rh.services.notificacoes import gerar_pendencias_do_dia
    gerar_pendencias_do_dia(dia)
    messages.success(request, "Registro excluído.")
    return redirect(request.META.get("HTTP_REFERER") or "rh:registros")


@perm_required("rh.ponto_gerir")
@require_POST
def view_abono_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove um abono — apenas super admin. O saldo do dia volta a contar."""
    if not request.user.is_superadmin:
        messages.error(request, "Apenas o super admin pode excluir abonos.")
        return redirect("rh:registros")
    a = get_object_or_404(AbonoPonto, pk=pk)
    a.delete()
    messages.success(request, "Abono excluído.")
    return redirect(request.META.get("HTTP_REFERER") or "rh:registros")
