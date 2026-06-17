"""
Filter `clean_html`: sanitiza HTML rico vindo do admin (ex: PaginaEstatica.conteudo)
permitindo tags de formatação comuns mas removendo <script>, handlers onXxx,
iframes não-autorizados, etc.

Uso no template:
    {% load safe_html %}
    {{ pagina.conteudo|clean_html }}
"""
from django import template
from django.utils.safestring import mark_safe
from apps.core_utils.sanitize import sanitize_rich_html

register = template.Library()


@register.filter(name='clean_html')
def clean_html(value):
    if not value:
        return ''
    try:
        limpo = sanitize_rich_html(value, max_length=100_000)
    except Exception:
        from django.utils.html import strip_tags
        limpo = strip_tags(str(value))
    return mark_safe(limpo)
