from datetime import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import Colaborador, Escala, EscalaDia, EscalaExcecao

DIAS = EscalaDia.DIA_CHOICES  # [(0, "Segunda"), ...]


@perm_required("rh.gerir")
def view_escalas(request: HttpRequest) -> HttpResponse:
    escalas = Escala.objects.all().prefetch_related("colaboradores")
    return render(request, "rh/escalas.html", {"escalas": escalas})


def _parse_hora(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None


@perm_required("rh.gerir")
def view_escala_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    obj = get_object_or_404(Escala, pk=pk) if pk else None

    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        if not nome:
            messages.error(request, "O nome da escala é obrigatório.")
        else:
            alterna = request.POST.get("alterna_sabado") == "on"
            ativo = request.POST.get("ativo") == "on"
            if obj:
                obj.nome, obj.alterna_sabado, obj.ativo = nome, alterna, ativo
                obj.save()
            else:
                obj = Escala.objects.create(nome=nome, alterna_sabado=alterna, ativo=ativo)

            variantes = ["A", "B"] if alterna else ["A"]
            # Limpa a variante B se a escala deixou de alternar.
            if not alterna:
                EscalaDia.objects.filter(escala=obj, variante="B").delete()

            for variante in variantes:
                for dia, _label in DIAS:
                    trabalha = request.POST.get(f"trab_{variante}_{dia}") == "on"
                    entrada = _parse_hora(request.POST.get(f"ent_{variante}_{dia}"))
                    saida = _parse_hora(request.POST.get(f"sai_{variante}_{dia}"))
                    alm_ini = _parse_hora(request.POST.get(f"almi_{variante}_{dia}"))
                    alm_fim = _parse_hora(request.POST.get(f"almf_{variante}_{dia}"))
                    EscalaDia.objects.update_or_create(
                        escala=obj, variante=variante, dia_semana=dia,
                        defaults={
                            "trabalha": trabalha, "hora_entrada": entrada, "hora_saida": saida,
                            "hora_saida_almoco": alm_ini, "hora_volta_almoco": alm_fim,
                        },
                    )
            messages.success(request, f'Escala "{nome}" salva.')
            return redirect("rh:escalas")

    # Monta a matriz dias × variantes para o template
    existentes = {}
    if obj:
        existentes = {(d.variante, d.dia_semana): d for d in obj.dias.all()}

    def linhas(variante):
        return [
            {"dia": dia, "label": label, "ed": existentes.get((variante, dia))}
            for dia, label in DIAS
        ]

    return render(request, "rh/escala_form.html", {
        "obj": obj,
        "linhas_a": linhas("A"),
        "linhas_b": linhas("B"),
    })


@perm_required("rh.gerir")
@require_POST
def view_escala_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Escala, pk=pk)
    if obj.colaboradores.exists():
        messages.error(request, "Não é possível excluir: há colaboradoras vinculadas.")
    else:
        nome = obj.nome
        obj.delete()
        messages.success(request, f'Escala "{nome}" excluída.')
    return redirect("rh:escalas")


@perm_required("rh.gerir")
def view_escala_excecoes(request: HttpRequest) -> HttpResponse:
    """Trocas de sábado: força a variante de uma semana para uma colaboradora."""
    if request.method == "POST":
        colab = get_object_or_404(Colaborador, pk=request.POST.get("colaborador"))
        data_raw = request.POST.get("semana") or ""
        variante = request.POST.get("variante", "A")
        try:
            d = datetime.strptime(data_raw, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Informe uma data válida.")
            return redirect("rh:escala_excecoes")
        from datetime import timedelta
        segunda = d - timedelta(days=d.weekday())
        EscalaExcecao.objects.update_or_create(
            colaborador=colab, semana_segunda=segunda,
            defaults={"variante": variante, "observacao": request.POST.get("observacao", "").strip()},
        )
        messages.success(request, f"Exceção salva para a semana de {segunda:%d/%m/%Y}.")
        return redirect("rh:escala_excecoes")

    colaboradores = list(
        Colaborador.objects.filter(ativo=True, escala__alterna_sabado=True).order_by("nome")
    )
    excecoes = EscalaExcecao.objects.select_related("colaborador").all()
    return render(request, "rh/escala_excecoes.html", {
        "colaboradores": colaboradores,
        "excecoes": excecoes,
        "variantes": EscalaDia.VARIANTE_CHOICES,
    })


@perm_required("rh.gerir")
@require_POST
def view_escala_excecao_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    exc = get_object_or_404(EscalaExcecao, pk=pk)
    exc.delete()
    messages.success(request, "Exceção removida.")
    return redirect("rh:escala_excecoes")
