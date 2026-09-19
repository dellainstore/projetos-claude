"""Página diagnóstica do escritório virtual (fase 4).

Ainda NÃO é o cenário definitivo: é uma tabela ao vivo que mostra o que a
projeção está devolvendo, para validar o poller e o contrato da API antes de
existir mapa, sprite ou animação. O Phaser entra numa fase seguinte,
consumindo exatamente o mesmo endpoint.
"""

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.core.decorators import perm_required
from apps.escritorio_virtual.models import ParametrosEscritorio
from apps.escritorio_virtual.views.api import PERM_VER


@require_GET
@perm_required(PERM_VER)
def view_diagnostico(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "ESCRITORIO_ATIVO", True):
        raise Http404("Escritório virtual desativado.")
    parametros = ParametrosEscritorio.atual()
    return render(request, "escritorio/diagnostico.html", {
        "poll_segundos": parametros.poll_segundos,
    })
