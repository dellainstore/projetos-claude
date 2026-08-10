"""Regras de visibilidade, edição e histórico do quadro de Tarefas.

Visibilidade: cada usuário só enxerga cards em que é responsável ou criador;
Super Admin (`user.is_superadmin`) vê todos. Nunca aplicar filtro de módulo
(`tarefas.ver`) sozinho como se fosse suficiente para liberar ver tudo — é
exatamente esse tipo de checagem manual solta que já causou o bug de IDOR
documentado em apps/core/views.py.
"""
from django.db.models import Q

from apps.tarefas.models import ColunaStatus, HistoricoTarefa, Tarefa, TarefaResponsavel


def tarefas_visiveis(user, incluir_arquivadas=False):
    qs = Tarefa.objects.select_related("status", "criado_por").prefetch_related("responsaveis")
    if not incluir_arquivadas:
        qs = qs.filter(arquivada=False)
    if user.is_superadmin:
        return qs
    return qs.filter(Q(responsaveis=user) | Q(criado_por=user)).distinct()


def pode_mover_status(tarefa, user) -> bool:
    """Responsável(is), criador ou Super Admin podem arrastar o card entre colunas."""
    if user.is_superadmin or user.pk == tarefa.criado_por_id:
        return True
    return tarefa.responsaveis.filter(pk=user.pk).exists()


def pode_editar_conteudo(tarefa, user) -> bool:
    """Só quem criou a tarefa (ou Super Admin) edita título/descrição/prazo/
    prioridade/responsáveis — evita que o pedido original seja alterado por
    quem só recebeu a tarefa. Mover de coluna é outra permissão (acima)."""
    return user.is_superadmin or user.pk == tarefa.criado_por_id


def pode_excluir(tarefa, user) -> bool:
    """Só quem criou a tarefa ou o Super Admin pode excluir (arquivar) de verdade."""
    return user.is_superadmin or user.pk == tarefa.criado_por_id


def foi_editado_e_nao_visto(tarefa, user) -> bool:
    """True quando o criador editou o conteúdo depois da última vez que
    `user` (um dos responsáveis) abriu o card — vira o selo "Editado" no
    board, pra nunca mudar o pedido sem a pessoa perceber."""
    if not tarefa.editado_em:
        return False
    vinculo = TarefaResponsavel.objects.filter(tarefa=tarefa, usuario=user).first()
    if not vinculo:
        return False
    return vinculo.visto_em is None or vinculo.visto_em < tarefa.editado_em


def registrar_historico(tarefa, campo, valor_anterior, valor_novo, usuario) -> None:
    if str(valor_anterior) == str(valor_novo):
        return
    HistoricoTarefa.objects.create(
        tarefa=tarefa,
        campo=campo,
        valor_anterior=str(valor_anterior)[:255],
        valor_novo=str(valor_novo)[:255],
        alterado_por=usuario,
    )


def _aplicar_filtros_comuns(qs, pessoa_id=None, texto=None):
    if pessoa_id:
        qs = qs.filter(responsaveis__pk=pessoa_id).distinct()
    if texto:
        qs = qs.filter(Q(titulo__icontains=texto) | Q(descricao__icontains=texto))
    return qs


def montar_quadro(user, pessoa_id=None, texto=None, prazo_de=None, prazo_ate=None):
    """Monta a estrutura de colunas + cards do quadro visível para `user`,
    com os filtros opcionais de pessoa/texto/prazo já aplicados."""
    tarefas = _aplicar_filtros_comuns(tarefas_visiveis(user), pessoa_id, texto)
    if prazo_de:
        tarefas = tarefas.filter(prazo__gte=prazo_de)
    if prazo_ate:
        tarefas = tarefas.filter(prazo__lte=prazo_ate)

    colunas = list(ColunaStatus.objects.filter(ativa=True))
    tarefas = list(tarefas)
    return [
        {"coluna": c, "tarefas": [t for t in tarefas if t.status_id == c.id]}
        for c in colunas
    ]


def listar_historico(user, pessoa_id=None, texto=None, data_de=None, data_ate=None, motivo=None):
    """Tarefas arquivadas (concluídas há mais de N dias ou excluídas) que
    `user` pode ver — mesma regra de visibilidade do quadro ativo."""
    qs = _aplicar_filtros_comuns(
        tarefas_visiveis(user, incluir_arquivadas=True).filter(arquivada=True),
        pessoa_id, texto,
    )
    if data_de:
        qs = qs.filter(arquivada_em__date__gte=data_de)
    if data_ate:
        qs = qs.filter(arquivada_em__date__lte=data_ate)
    if motivo:
        qs = qs.filter(motivo_arquivamento=motivo)
    return qs.order_by("-arquivada_em")
