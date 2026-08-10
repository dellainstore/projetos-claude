from django import template

register = template.Library()


@register.filter
def primeiro_nome(user):
    """Só o primeiro nome (ou username, se não tiver nome cadastrado) — o
    quadro é pra equipe pequena, nome completo é ruído desnecessário."""
    if not user:
        return ""
    return user.first_name or user.username


@register.filter
def editado_nao_visto(tarefa, user):
    """True se `tarefa` foi editada pelo criador depois da última vez que
    `user` (responsável) abriu o card — usado pra mostrar o selo "Editado"
    no board, avisando quem ainda não viu a mudança."""
    from apps.tarefas.services.regras import foi_editado_e_nao_visto
    return foi_editado_e_nao_visto(tarefa, user)
