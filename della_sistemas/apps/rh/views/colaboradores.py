from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.contrib.auth import get_user_model

from apps.core.decorators import perm_required
from apps.rh.models import Colaborador, Escala, LocalEmpresa
from apps.rh.services.utils import parse_decimal as _parse_decimal
from apps.rh.services.utils import parse_int as _parse_int

User = get_user_model()


@perm_required("rh.gerir")
def view_colaboradores(request: HttpRequest) -> HttpResponse:
    colaboradores = Colaborador.objects.order_by("nome")
    return render(request, "rh/colaboradores.html", {"colaboradores": colaboradores})


def _usuarios_disponiveis(obj):
    """Usuários ativos que ainda não estão vinculados a outro colaborador
    (mais o usuário já vinculado a este, para não sumir do select)."""
    vinculados = set(
        Colaborador.objects.exclude(pk=obj.pk if obj else None)
        .exclude(usuario__isnull=True)
        .values_list("usuario_id", flat=True)
    )
    return User.objects.filter(is_active=True).exclude(id__in=vinculados).order_by("username")


@perm_required("rh.gerir")
def view_colaborador_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    obj = get_object_or_404(Colaborador, pk=pk) if pk else None

    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        usuario_raw = request.POST.get("usuario", "").strip()
        usuario_id = int(usuario_raw) if usuario_raw.isdigit() else None
        # Impede vincular o mesmo login a dois colaboradores.
        conflito = (
            usuario_id and Colaborador.objects
            .exclude(pk=obj.pk if obj else None)
            .filter(usuario_id=usuario_id).exists()
        )
        if not nome:
            messages.error(request, "O nome é obrigatório.")
        elif conflito:
            messages.error(request, "Esse login já está vinculado a outro colaborador.")
        else:
            cargo = request.POST.get("cargo", "").strip()
            tipo = request.POST.get("tipo_contrato", "clt")
            bling_raw = request.POST.get("bling_vendedor_id", "").strip()
            bling_id = int(bling_raw) if bling_raw.isdigit() else None
            admissao = request.POST.get("data_admissao") or None
            salario = _parse_decimal(request.POST.get("salario_base", ""))
            pct = _parse_decimal(request.POST.get("comissao_percentual_padrao", ""), Decimal("4.5"))
            recebe_comissao = request.POST.get("recebe_comissao") == "on"
            recebe_vt = request.POST.get("recebe_vt") == "on"
            vt = _parse_decimal(request.POST.get("vt_valor_dia", ""))
            carga_raw = request.POST.get("carga_horaria_diaria", "").strip()
            carga = _parse_decimal(carga_raw) if carga_raw else None
            escala_raw = request.POST.get("escala", "").strip()
            escala_id = int(escala_raw) if escala_raw.isdigit() else None
            ancora = request.POST.get("escala_ancora_b") or None
            vt_adiant = _parse_int(request.POST.get("vt_meses_adiantado", ""), 1)
            na_folha = request.POST.get("na_folha") == "on"
            registra_ponto = request.POST.get("registra_ponto") == "on"
            ativo = request.POST.get("ativo") == "on"
            lojas_ids = [int(x) for x in request.POST.getlist("lojas_ponto") if x.isdigit()]

            campos = dict(
                nome=nome, cargo=cargo, tipo_contrato=tipo, usuario_id=usuario_id,
                bling_vendedor_id=bling_id, data_admissao=admissao,
                salario_base=salario,
                recebe_comissao=recebe_comissao, comissao_percentual_padrao=pct,
                recebe_vt=recebe_vt, vt_valor_dia=vt, carga_horaria_diaria=carga,
                escala_id=escala_id, escala_ancora_b=ancora, vt_meses_adiantado=vt_adiant,
                na_folha=na_folha, registra_ponto=registra_ponto, ativo=ativo,
            )
            if obj:
                for k, v in campos.items():
                    setattr(obj, k, v)
                obj.save()
                obj.lojas_ponto.set(lojas_ids)
                messages.success(request, f'Colaborador "{nome}" atualizado.')
            else:
                obj = Colaborador.objects.create(**campos)
                obj.lojas_ponto.set(lojas_ids)
                messages.success(request, f'Colaborador "{nome}" cadastrado.')
            return redirect("rh:colaboradores")

    return render(request, "rh/colaborador_form.html", {
        "obj": obj,
        "tipos": Colaborador.TIPO_CHOICES,
        "escalas": Escala.objects.filter(ativo=True).order_by("nome"),
        "usuarios": _usuarios_disponiveis(obj),
        "lojas": LocalEmpresa.objects.filter(ativo=True).order_by("nome"),
        "lojas_vinculadas": set(obj.lojas_ponto.values_list("id", flat=True)) if obj else set(),
    })


@perm_required("rh.gerir")
@require_POST
def view_colaborador_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Colaborador, pk=pk)
    obj.ativo = not obj.ativo
    obj.save(update_fields=["ativo"])
    messages.success(request, f'Colaborador "{obj.nome}" {"ativado" if obj.ativo else "desativado"}.')
    return redirect("rh:colaboradores")
