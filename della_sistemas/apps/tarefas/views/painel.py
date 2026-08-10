from datetime import date

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.tarefas.models import ColunaStatus
from apps.tarefas.services.regras import montar_quadro

User = get_user_model()


@perm_required("tarefas.ver")
def view_painel(request: HttpRequest) -> HttpResponse:
    pessoa_id = request.GET.get("pessoa", "").strip()
    texto = request.GET.get("q", "").strip()
    prazo_de = request.GET.get("prazo_de", "").strip()
    prazo_ate = request.GET.get("prazo_ate", "").strip()

    quadro = montar_quadro(
        request.user,
        pessoa_id=int(pessoa_id) if pessoa_id.isdigit() else None,
        texto=texto or None,
        prazo_de=prazo_de or None,
        prazo_ate=prazo_ate or None,
    )

    return render(request, "tarefas/painel.html", {
        "quadro": quadro,
        "colunas": ColunaStatus.objects.filter(ativa=True),
        "pessoa_id": pessoa_id,
        "f_q": texto,
        "f_prazo_de": prazo_de,
        "f_prazo_ate": prazo_ate,
        "usuarios_atribuiveis": User.objects.filter(is_active=True).order_by("first_name", "username"),
        "hoje": date.today(),
    })
