"""
Sitemap.xml + robots.txt servidos pela aplicacao.
Sem dependencia de django.contrib.sites (evita migration nova).
"""

from django.http import HttpResponse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from xml.sax.saxutils import escape as xml_escape

from .models import Categoria, Produto


def _absolute(request, path):
    return f"{request.scheme}://{request.get_host()}{path}"


def _url_entry(loc, lastmod=None, changefreq=None, priority=None):
    parts = [f"  <url>", f"    <loc>{xml_escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>")
    if changefreq:
        parts.append(f"    <changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"    <priority>{priority}</priority>")
    parts.append("  </url>")
    return "\n".join(parts)


@cache_page(60 * 60 * 6)
def sitemap_xml(request):
    hoje = now()
    entries = []

    # Home + paginas institucionais
    institucionais = [
        ('produtos:home', 'daily', '1.0'),
        ('produtos:loja', 'daily', '0.9'),
        ('produtos:sobre', 'monthly', '0.5'),
        ('produtos:contato', 'monthly', '0.5'),
        ('produtos:politica_privacidade', 'yearly', '0.3'),
        ('produtos:termos_uso', 'yearly', '0.3'),
        ('produtos:trocas_devolucoes', 'yearly', '0.4'),
        ('produtos:perguntas_frequentes', 'monthly', '0.4'),
        ('produtos:meios_pagamento', 'yearly', '0.3'),
        ('produtos:guia_tamanhos', 'yearly', '0.3'),
    ]
    for url_name, freq, prio in institucionais:
        try:
            path = reverse(url_name)
            entries.append(_url_entry(_absolute(request, path), hoje, freq, prio))
        except Exception:
            pass

    # Categorias ativas (com parent ou nao)
    for cat in Categoria.objects.filter(ativa=True).order_by('parent_id', 'nome'):
        try:
            entries.append(_url_entry(
                _absolute(request, cat.get_absolute_url()),
                hoje, 'weekly', '0.7'
            ))
        except Exception:
            pass

    # Produtos ativos
    produtos = (
        Produto.objects
        .filter(ativo=True, categoria__ativa=True)
        .only('slug', 'atualizado_em')
        .order_by('-atualizado_em')
    )
    for p in produtos:
        try:
            entries.append(_url_entry(
                _absolute(request, p.get_absolute_url()),
                p.atualizado_em, 'weekly', '0.8'
            ))
        except Exception:
            pass

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    return HttpResponse(xml, content_type='application/xml')


def robots_txt(request):
    host = request.get_host()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /painel/\n"
        "Disallow: /admin/\n"
        "Disallow: /carrinho/\n"
        "Disallow: /conta/\n"
        "Disallow: /pagamento/\n"
        "Disallow: /bling/\n"
        "Disallow: /busca/\n"
        "\n"
        f"Sitemap: {request.scheme}://{host}/sitemap.xml\n"
    )
    return HttpResponse(body, content_type='text/plain; charset=utf-8')
