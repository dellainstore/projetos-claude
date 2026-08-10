from functools import wraps

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.tarefas.models import ColunaStatus


def _superadmin_obrigatorio(view_func):
    """Gestão de colunas é configuração estrutural do módulo — igual ao bloco
    'Administração' do menu, gate direto por is_superadmin, sem permissão
    própria."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("core:login")
        if not request.user.is_superadmin:
            messages.error(request, "Só o Super Admin pode configurar as colunas de status.")
            return redirect("tarefas:painel")
        return view_func(request, *args, **kwargs)
    return wrapper


@_superadmin_obrigatorio
def view_colunas(request: HttpRequest) -> HttpResponse:
    return render(request, "tarefas/colunas.html", {
        "colunas": ColunaStatus.objects.order_by("ordem", "pk"),
    })


@_superadmin_obrigatorio
def htmx_criar_coluna(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        if nome:
            ColunaStatus.objects.create(nome=nome, ordem=ColunaStatus.objects.count())
            messages.success(request, "Coluna criada.")
        else:
            messages.error(request, "Informe um nome para a coluna.")
    return render(request, "tarefas/_colunas_lista.html", {
        "colunas": ColunaStatus.objects.order_by("ordem", "pk"),
    })


@_superadmin_obrigatorio
def htmx_editar_coluna(request: HttpRequest, pk: int) -> HttpResponse:
    coluna = get_object_or_404(ColunaStatus, pk=pk)
    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        if nome:
            coluna.nome = nome
        coluna.eh_conclusao = request.POST.get("eh_conclusao") == "1"
        coluna.ativa = request.POST.get("ativa") == "1"
        coluna.save()
        messages.success(request, "Coluna atualizada.")
    return render(request, "tarefas/_colunas_lista.html", {
        "colunas": ColunaStatus.objects.order_by("ordem", "pk"),
    })


@_superadmin_obrigatorio
def htmx_reordenar_colunas(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        mover_id = request.POST.get("mover", "")
        direcao = request.POST.get("direcao", "")
        colunas = list(ColunaStatus.objects.order_by("ordem", "pk"))
        idx = next((i for i, c in enumerate(colunas) if str(c.pk) == mover_id), None)
        if idx is not None:
            novo_idx = idx - 1 if direcao == "cima" else idx + 1 if direcao == "baixo" else idx
            if 0 <= novo_idx < len(colunas) and novo_idx != idx:
                colunas[idx], colunas[novo_idx] = colunas[novo_idx], colunas[idx]
                for posicao, c in enumerate(colunas):
                    if c.ordem != posicao:
                        c.ordem = posicao
                        c.save(update_fields=["ordem"])
    return render(request, "tarefas/_colunas_lista.html", {
        "colunas": ColunaStatus.objects.order_by("ordem", "pk"),
    })
