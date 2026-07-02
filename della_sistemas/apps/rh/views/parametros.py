"""Parâmetros do ponto: lojas (geofence), tolerância e vínculo colaborador↔loja."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import Colaborador, LocalEmpresa, ParametrosPonto
from apps.rh.services.utils import parse_decimal, parse_int


@perm_required("rh.ponto_gerir")
def view_parametros(request: HttpRequest) -> HttpResponse:
    lojas = list(LocalEmpresa.objects.order_by("-ativo", "nome"))
    colaboradores = list(Colaborador.objects.filter(ativo=True).order_by("nome"))
    # Anexa os IDs de loja vinculados a cada colaborador (usado na matriz).
    for c in colaboradores:
        c.lojas_ids = set(c.lojas_ponto.values_list("id", flat=True))
    return render(request, "rh/parametros.html", {
        "lojas": lojas,
        "colaboradores": colaboradores,
        "parametros": ParametrosPonto.get(),
    })


@perm_required("rh.ponto_gerir")
@require_POST
def view_tolerancia_salvar(request: HttpRequest) -> HttpResponse:
    p = ParametrosPonto.get()
    p.tolerancia_minutos = max(parse_int(request.POST.get("tolerancia_minutos"), 10), 0)
    p.intervalo_minimo_minutos = max(parse_int(request.POST.get("intervalo_minimo_minutos"), 2), 0)
    p.save(update_fields=["tolerancia_minutos", "intervalo_minimo_minutos"])
    messages.success(request, "Regras do ponto salvas.")
    return redirect("rh:parametros")


@perm_required("rh.ponto_gerir")
def view_loja_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    obj = get_object_or_404(LocalEmpresa, pk=pk) if pk else None
    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        lat = parse_decimal(request.POST.get("latitude", ""))
        lon = parse_decimal(request.POST.get("longitude", ""))
        raio = max(parse_int(request.POST.get("raio_metros"), 100), 1)
        ativo = request.POST.get("ativo") == "on"
        if not nome or not lat or not lon:
            messages.error(request, "Nome, latitude e longitude são obrigatórios.")
        else:
            campos = dict(nome=nome, latitude=lat, longitude=lon, raio_metros=raio, ativo=ativo)
            if obj:
                for k, v in campos.items():
                    setattr(obj, k, v)
                obj.save()
                messages.success(request, f'Loja "{nome}" atualizada.')
            else:
                LocalEmpresa.objects.create(**campos)
                messages.success(request, f'Loja "{nome}" cadastrada.')
            return redirect("rh:parametros")
    return render(request, "rh/loja_form.html", {"obj": obj})


@perm_required("rh.ponto_gerir")
@require_POST
def view_loja_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(LocalEmpresa, pk=pk)
    nome = obj.nome
    obj.delete()
    messages.success(request, f'Loja "{nome}" excluída.')
    return redirect("rh:parametros")


@perm_required("rh.ponto_gerir")
@require_POST
def view_vinculos_salvar(request: HttpRequest) -> HttpResponse:
    """Salva a matriz colaborador↔loja. Cada checkbox tem name='vinc_<colab>_<loja>'."""
    lojas = list(LocalEmpresa.objects.values_list("id", flat=True))
    for colaborador in Colaborador.objects.filter(ativo=True):
        marcadas = [
            lid for lid in lojas
            if request.POST.get(f"vinc_{colaborador.id}_{lid}") == "on"
        ]
        colaborador.lojas_ponto.set(marcadas)
    messages.success(request, "Vínculos de loja atualizados.")
    return redirect("rh:parametros")
