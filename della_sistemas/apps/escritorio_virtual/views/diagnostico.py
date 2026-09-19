"""Página do escritório virtual: cena Phaser sobre a imagem de fundo real.

A projeção continua vindo só da API (`/escritorio/api/estado/`); esta view
só decide QUAL ARQUIVO de imagem servir como fundo.
"""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.core.decorators import perm_required
from apps.escritorio_virtual.models import ParametrosEscritorio
from apps.escritorio_virtual.views.api import PERM_VER

# Nome do arquivo da arte oficial, quando aprovada e salva no repositório.
# Enquanto ele não existir em `static/escritorio/`, a página cai sozinha no
# placeholder — nenhuma edição de template ou de view é necessária no dia em
# que o arquivo chegar, só salvar o PNG com este nome exato.
_BG_OFICIAL = "escritorio/office-bg.png"
_BG_PLACEHOLDER = "escritorio/office-bg-placeholder.svg"


def _bg_estatico() -> str:
    caminho_oficial = Path(settings.BASE_DIR) / "static" / "escritorio" / "office-bg.png"
    return _BG_OFICIAL if caminho_oficial.is_file() else _BG_PLACEHOLDER


@require_GET
@perm_required(PERM_VER)
def view_diagnostico(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "ESCRITORIO_ATIVO", True):
        raise Http404("Escritório virtual desativado.")
    parametros = ParametrosEscritorio.atual()
    return render(request, "escritorio/diagnostico.html", {
        "poll_segundos": parametros.poll_segundos,
        "bg_estatico": _bg_estatico(),
        # Painel de simulação: só para quem administra o cenário. Ele não
        # cria batida nem chama endpoint de escrita (ver ui/DebugPanel.ts),
        # mas mostra estados que não são os reais, então não deve aparecer
        # para quem só assiste.
        "pode_simular": request.user.tem_perm("escritorio.configurar"),
    })
