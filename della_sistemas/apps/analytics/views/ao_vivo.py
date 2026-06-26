from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required


@perm_required("analytics.ver")
def ao_vivo(request: HttpRequest) -> HttpResponse:
    dados = {'visitantes': 0, 'paginas': []}

    if 'della_site' in settings.DATABASES:
        try:
            from apps.analytics.views.dashboard import _calcular_ao_vivo
            dados = _calcular_ao_vivo()
        except Exception:
            pass

    return render(request, 'analytics/_ao_vivo.html', {'ao_vivo': dados})
