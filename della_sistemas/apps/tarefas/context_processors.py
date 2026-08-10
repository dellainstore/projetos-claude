"""Contador de tarefas pendentes atribuídas ao usuário — alimenta o badge
do menu/card (sem e-mail, só painel, por decisão do usuário)."""


def tarefas_pendencias(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "pode_ver_tarefas", False):
        return {}

    from apps.tarefas.services.regras import tarefas_visiveis

    qs = (
        tarefas_visiveis(user)
        .filter(responsaveis=user, status__eh_conclusao=False)
        .distinct()
    )
    return {"tarefas_pendentes_count": qs.count()}
