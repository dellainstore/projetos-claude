"""Contador de tarefas pendentes atribuídas ao usuário — alimenta o badge
do menu/card (sem e-mail, só painel, por decisão do usuário).

Conta só o que ainda não foi visto: uma tarefa some do contador assim que a
pessoa abre o card (ou responde/edita, que já marca como visto pra ela
mesma) — e some pra ela mas passa a contar pra quem ainda não viu a resposta.
Ver tem_atividade_nao_vista() em services/regras.py."""


def tarefas_pendencias(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "pode_ver_tarefas", False):
        return {}

    from apps.tarefas.services.regras import tarefas_visiveis, tem_atividade_nao_vista

    qs = (
        tarefas_visiveis(user)
        .filter(responsaveis=user, status__eh_conclusao=False)
        .distinct()
    )
    count = sum(1 for t in qs if tem_atividade_nao_vista(t, user))
    return {"tarefas_pendentes_count": count}
