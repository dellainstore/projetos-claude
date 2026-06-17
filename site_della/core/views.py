import json
import logging

from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger('django.security')


@csrf_exempt
@require_POST
def csp_report(request):
    """Recebe violacoes de CSP reportadas pelo browser e registra no security.log."""
    try:
        payload = json.loads(request.body)
        report = payload.get('csp-report', payload)
        logger.warning(
            'CSP violation: blocked-uri=%s violated-directive=%s document-uri=%s',
            report.get('blocked-uri', '?'),
            report.get('violated-directive', '?'),
            report.get('document-uri', '?'),
        )
    except Exception:
        logger.warning('CSP violation report recebido mas nao parseado: %r', request.body[:500])
    return HttpResponse(status=204)


def handler404(request, exception=None):
    path = request.path.strip('/').lower()

    # Remove extensoes de plataformas antigas (.html, .php, .asp)
    for ext in ('.html', '.php', '.asp', '.aspx'):
        if path.endswith(ext):
            path = path[:-len(ext)]

    # Redireciona URLs antigas de carrinho para o carrinho atual
    if path.startswith('carrinho/produto/') or path.startswith('cart/'):
        return redirect('/carrinho/', permanent=True)

    # Redireciona URLs antigas de marca/fornecedor para a loja
    if path.startswith('marca/') or path.startswith('brand/') or path.startswith('fabricante/'):
        return redirect('/loja/', permanent=True)

    # Redireciona URLs antigas de busca/tag para a loja
    if path.startswith('busca/') or path.startswith('tag/') or path.startswith('search/'):
        return redirect('/loja/', permanent=True)

    # Verifica se o slug bate com um produto existente
    if path:
        try:
            from apps.produtos.models import Produto, Categoria
            produto = Produto.objects.filter(slug=path, ativo=True).first()
            if produto:
                return redirect(f'/produto/{produto.slug}/', permanent=True)

            # Verifica se o slug bate com uma categoria existente
            categoria = Categoria.objects.filter(slug=path, ativa=True).first()
            if categoria:
                return redirect(f'/loja/{categoria.slug}/', permanent=True)
        except Exception:
            logging.getLogger(__name__).debug('Erro ao resolver slug no handler404: %s', request.path, exc_info=True)

    return TemplateResponse(request, '404.html', status=404)
