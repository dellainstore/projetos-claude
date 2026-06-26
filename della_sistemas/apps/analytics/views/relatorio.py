import os
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.analytics.models import RelatorioSemanal
from apps.core.decorators import perm_required


@perm_required("analytics.ver")
def relatorio_list(request: HttpRequest) -> HttpResponse:
    relatorios = RelatorioSemanal.objects.all()
    return render(request, 'analytics/relatorio_list.html', {
        'relatorios': relatorios,
    })


@perm_required("analytics.ver")
def relatorio_download(request: HttpRequest, pk: int) -> FileResponse:
    rel = get_object_or_404(RelatorioSemanal, pk=pk)
    filepath = Path(settings.MEDIA_ROOT) / rel.arquivo
    if not filepath.exists():
        raise Http404("PDF nao encontrado no servidor.")
    response = FileResponse(open(filepath, 'rb'), content_type='application/pdf')
    nome = filepath.name
    response['Content-Disposition'] = f'attachment; filename="{nome}"'
    return response
