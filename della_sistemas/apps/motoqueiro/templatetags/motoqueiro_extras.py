from django import template

register = template.Library()

_STATUS_CSS = {
    "aguardando_coleta": "ds-status--pendente",
    "no_percurso": "ds-status--processado",
    "entrega_realizada": "ds-status--aprovado",
    "problema_entrega": "ds-status--rejeitado",
    "problema_coleta": "ds-status--rejeitado",
}


@register.filter
def status_css(status: str) -> str:
    return _STATUS_CSS.get(status, "")
