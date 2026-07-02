"""Context processors globais (disponíveis em todos os templates)."""


def ponto_pendencias(request):
    """Pendências de ponto do colaborador logado — alimenta o sino do header."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    colaborador = getattr(user, "colaborador", None)
    if colaborador is None:
        return {}
    from apps.rh.models import NotificacaoPonto
    qs = (
        NotificacaoPonto.objects.filter(colaborador=colaborador)
        .exclude(status="resolvido").order_by("-data")
    )
    return {
        "sino_pendencias": list(qs[:10]),
        "sino_pendencias_count": qs.count(),
    }
