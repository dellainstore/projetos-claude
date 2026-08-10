from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.tarefas.services.regras import listar_historico

User = get_user_model()


@perm_required("tarefas.ver")
def view_historico(request: HttpRequest) -> HttpResponse:
    pessoa_id = request.GET.get("pessoa", "").strip()
    texto = request.GET.get("q", "").strip()
    data_de = request.GET.get("data_de", "").strip()
    data_ate = request.GET.get("data_ate", "").strip()
    motivo = request.GET.get("motivo", "").strip()

    tarefas = listar_historico(
        request.user,
        pessoa_id=int(pessoa_id) if pessoa_id.isdigit() else None,
        texto=texto or None,
        data_de=data_de or None,
        data_ate=data_ate or None,
        motivo=motivo or None,
    )

    return render(request, "tarefas/historico.html", {
        "tarefas": tarefas,
        "usuarios_atribuiveis": User.objects.filter(is_active=True).order_by("first_name", "username"),
        "f_pessoa": pessoa_id,
        "f_q": texto,
        "f_data_de": data_de,
        "f_data_ate": data_ate,
        "f_motivo": motivo,
    })
