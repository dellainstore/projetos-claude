"""
Views do painel de Monitoramento (somente leitura).

Acesso: staff + permissão core_utils.ver_monitoramento (superusuário implícito).
Verificação feita em cada view via decorator — nunca só escondendo o menu.
Nenhuma view executa comando de shell, restart ou edição; apenas leitura
agregada e sanitizada.
"""
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.core_utils import monitoramento as monit

_PERMISSAO = 'core_utils.ver_monitoramento'


def _requer_monitoramento(view):
    @wraps(view)
    @staff_member_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_perm(_PERMISSAO):
            raise PermissionDenied('Sem permissão para acessar o Monitoramento.')
        return view(request, *args, **kwargs)
    return wrapper


def _titulo(ctx):
    ctx.setdefault('site_header', 'Della Instore: Administracao')
    return ctx


@_requer_monitoramento
def index(request):
    """Visão geral: cards de 5xx, saúde do sistema e integrações."""
    contexto = _titulo({
        'resumo': monit.resumo_geral(),
        'saude': monit.saude_sistema(),
        'integracoes': monit.status_integracoes(),
        'titulo': 'Monitoramento',
    })
    return render(request, 'admin/monitoramento/index.html', contexto)


@_requer_monitoramento
def erros(request):
    """Tabela filtrável de erros 5xx (agrupados por chave de deduplicação)."""
    try:
        horas = int(request.GET.get('horas', '168'))
    except (TypeError, ValueError):
        horas = 168
    horas = max(1, min(horas, 24 * 30))  # teto de 30 dias

    filtros = {}
    if request.GET.get('status'):
        try:
            filtros['status'] = int(request.GET['status'])
        except (TypeError, ValueError):
            pass
    for campo in ('fonte', 'integracao', 'dispositivo'):
        if request.GET.get(campo):
            filtros[campo] = request.GET[campo][:40]
    if request.GET.get('rota'):
        filtros['endpoint_contem'] = request.GET['rota'][:120]

    eventos = monit.ler_eventos(horas=horas, filtros=filtros)
    agrupados = monit.agregar(eventos)

    contexto = _titulo({
        'titulo': 'Erros 5xx',
        'grupos': agrupados[:200],
        'total_eventos': len(eventos),
        'total_grupos': len(agrupados),
        'horas': horas,
        'por_status': monit.resumo_por_status(eventos),
        'filtros': {
            'status': request.GET.get('status', ''),
            'fonte': request.GET.get('fonte', ''),
            'integracao': request.GET.get('integracao', ''),
            'dispositivo': request.GET.get('dispositivo', ''),
            'rota': request.GET.get('rota', ''),
        },
        'fontes': ('django', 'integracao', 'checkout', 'webhook', 'nginx'),
        'integracoes': monit.INTEGRACOES,
    })
    return render(request, 'admin/monitoramento/erros.html', contexto)


@_requer_monitoramento
def checkout(request):
    """Falhas específicas do checkout (fonte=checkout), incl. telemetria client."""
    eventos = monit.ler_eventos(horas=168, filtros={'fonte': 'checkout'})
    contexto = _titulo({
        'titulo': 'Monitoramento do Checkout',
        'eventos': eventos[:200],
        'total': len(eventos),
        'agrupados': monit.agregar(eventos)[:50],
    })
    return render(request, 'admin/monitoramento/checkout.html', contexto)
