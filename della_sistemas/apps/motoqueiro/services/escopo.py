from django.http import HttpRequest

from apps.motoqueiro.models import SolicitacaoEntrega


def qs_do_usuario(request: HttpRequest):
    """Escopo de visibilidade: quem tem `ver_todos` (gestor/superadmin) enxerga
    todo mundo; o restante só enxerga as próprias corridas (pelo colaborador
    vinculado ao próprio login)."""
    qs = SolicitacaoEntrega.objects.select_related("colaborador")
    if request.user.pode_ver_todas_motoqueiro:
        return qs
    colaborador = getattr(request.user, "colaborador", None)
    if not colaborador:
        return qs.none()
    return qs.filter(colaborador=colaborador)
