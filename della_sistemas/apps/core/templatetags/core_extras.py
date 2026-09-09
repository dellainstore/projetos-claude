import os
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders

register = template.Library()

# mtime resolvido uma vez por processo — o restart do gunicorn (obrigatorio
# no deploy) e o que renova o valor.
_VERSAO_ESTATICO = {}


@register.filter
def get_perm(d, key):
    """Acessa um valor de dict por chave dinâmica em templates."""
    if isinstance(d, dict):
        return d.get(key, {})
    return {}


@register.filter
def brl(value):
    """Formata número como moeda brasileira: R$ 1.894,00"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    inteiro = int(v)
    centavos = round((v - inteiro) * 100)
    inteiro_fmt = f"{inteiro:,}".replace(",", ".")
    return f"R$ {inteiro_fmt},{centavos:02d}"


@register.filter
def pct_css(value):
    """Percentual como string com ponto decimal — para uso em CSS width
    (LANGUAGE_CODE=pt-br faz floatformat/interpolação padrão usar vírgula,
    o que quebra silenciosamente `style="width:X%"`). Mesma implementação de
    `apps.metas.templatetags.metas_extras.pct_css`."""
    try:
        f = min(max(float(value), 0.0), 100.0)
        return f"{f:.1f}"
    except (TypeError, ValueError):
        return "0"


@register.simple_tag
def estatico(caminho):
    """URL de arquivo estático com ?v=<mtime> pra furar cache de browser.

    O nginx serve /static/ direto do disco sem mandar Cache-Control nenhum,
    então o browser aplica cache heurístico (~10% da idade do arquivo) e pode
    servir CSS/JS antigo por dias depois de um deploy — foi o que segurou o
    JS novo do quadro de Tarefas. O manifesto com hash no nome não resolve
    aqui: STATICFILES_STORAGE foi removido no Django 5.1 e o valor no
    settings.py está sendo ignorado, então collectstatic não gera nome com
    hash. O mtime do arquivo muda a cada deploy e faz o mesmo trabalho.
    """
    url = f"{settings.STATIC_URL}{caminho}"
    versao = _VERSAO_ESTATICO.get(caminho)
    if versao is None:
        origem = finders.find(caminho) or (Path(settings.STATIC_ROOT) / caminho)
        try:
            versao = str(int(os.path.getmtime(origem)))
        except OSError:
            versao = ""
        _VERSAO_ESTATICO[caminho] = versao
    return f"{url}?v={versao}" if versao else url
