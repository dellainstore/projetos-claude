"""
Filter `clean_html`: sanitiza HTML rico vindo do admin (ex: PaginaEstatica.conteudo)
permitindo tags de formatação comuns mas removendo <script>, handlers onXxx,
iframes não-autorizados, etc.

Uso no template:
    {% load safe_html %}
    {{ pagina.conteudo|clean_html }}
"""
import bleach
from bleach.css_sanitizer import CSSSanitizer
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_CSS_PROPS = [
    'color', 'background-color', 'background',
    'font-size', 'font-weight', 'font-style', 'font-family',
    'text-align', 'text-decoration', 'text-transform',
    'line-height', 'letter-spacing',
    'margin', 'margin-top', 'margin-bottom', 'margin-left', 'margin-right',
    'padding', 'padding-top', 'padding-bottom', 'padding-left', 'padding-right',
    'width', 'height', 'max-width', 'max-height',
    'border', 'border-radius', 'border-color', 'border-style', 'border-width',
    'display', 'float', 'clear',
]

_css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPS)

ALLOWED_TAGS = {
    'p', 'br', 'hr',
    'strong', 'em', 'u', 'b', 'i', 's', 'small', 'sub', 'sup',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote',
    'a', 'img', 'figure', 'figcaption',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption',
    'span', 'div',
}

ALLOWED_ATTRS = {
    '*':   ['class', 'style', 'id'],
    'a':   ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'loading'],
    'table': ['border', 'cellpadding', 'cellspacing'],
    'td':  ['colspan', 'rowspan', 'align'],
    'th':  ['colspan', 'rowspan', 'align', 'scope'],
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel']


@register.filter(name='clean_html')
def clean_html(value):
    if not value:
        return ''
    limpo = bleach.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_css_sanitizer,
        strip=True,
        strip_comments=True,
    )
    return mark_safe(limpo)
