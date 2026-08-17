from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.decorators import perm_required
from apps.tarefas.context_processors import tarefas_pendencias
from apps.tarefas.models import ColunaStatus, Tarefa, TarefaComentario, TarefaResponsavel
from apps.tarefas.services.regras import (
    foi_editado_e_nao_visto,
    montar_quadro,
    pode_editar_conteudo,
    pode_excluir,
    pode_mover_status,
    registrar_historico,
    responsaveis_removiveis,
    tarefas_visiveis,
)

User = get_user_model()


def _filtros_de(request: HttpRequest) -> dict:
    # Escritas (criar/editar/mover/arquivar) chegam via POST — o front injeta
    # os filtros atuais (lidos de location.search) como valores extra do
    # form/hx-vals, ver static/js/tarefas-kanban.js::tarefasFiltroValor().
    fonte = request.POST if request.method == "POST" else request.GET
    pessoa = fonte.get("pessoa", "").strip()
    return {
        "pessoa_id": int(pessoa) if pessoa.isdigit() else None,
        "texto": fonte.get("q", "").strip() or None,
        "prazo_de": fonte.get("prazo_de", "").strip() or None,
        "prazo_ate": fonte.get("prazo_ate", "").strip() or None,
    }


def _tarefa_visivel_ou_404(request: HttpRequest, pk: int) -> Tarefa:
    # incluir_arquivadas=True: quem já viu o card antes de ele ser arquivado
    # ainda consegue abrir o histórico; a visibilidade em si (responsável /
    # criador / Super Admin) continua sendo aplicada por tarefas_visiveis().
    return get_object_or_404(tarefas_visiveis(request.user, incluir_arquivadas=True), pk=pk)


def _resposta_board(request: HttpRequest) -> HttpResponse:
    return render(request, "tarefas/_board_fecha_modal.html", {
        "quadro": montar_quadro(request.user, **_filtros_de(request)),
    })


def _nomes(ids) -> str:
    return ", ".join(
        u.first_name or u.username
        for u in User.objects.filter(pk__in=ids).order_by("first_name", "username")
    )


def _set_responsaveis(tarefa: Tarefa, ids, usuario) -> list:
    """Aplica a lista de responsáveis pedida por `usuario` no formulário de
    edição. Acrescentar gente nova é sempre livre pra quem chega aqui (só
    entra quem já passou por pode_editar_conteudo). Já remover é restrito:
    quem criou a tarefa (ou Super Admin) tira qualquer um; um responsável
    comum só tira quem ele mesmo colocou — ver responsaveis_removiveis().
    Pedido de remoção sem permissão é ignorado (a pessoa continua no card) e
    os IDs bloqueados voltam pro chamador avisar quem não pôde ser tirado."""
    vinculos = {v.usuario_id: v for v in TarefaResponsavel.objects.filter(tarefa=tarefa)}
    antigos = set(vinculos)
    pedidos = set(ids)
    if antigos == pedidos:
        return []

    removiveis = responsaveis_removiveis(tarefa, usuario)
    removidos, bloqueados = set(), []
    for uid in antigos - pedidos:
        if uid in removiveis:
            vinculos[uid].delete()
            removidos.add(uid)
        else:
            bloqueados.append(uid)

    adicionados = pedidos - antigos
    for uid in adicionados:
        TarefaResponsavel.objects.get_or_create(
            tarefa=tarefa, usuario_id=uid, defaults={"adicionado_por": usuario},
        )

    final = (antigos - removidos) | adicionados
    if final != antigos:
        registrar_historico(tarefa, "responsaveis", _nomes(antigos), _nomes(final), usuario)
    return bloqueados


@perm_required("tarefas.ver")
def htmx_board(request: HttpRequest) -> HttpResponse:
    """Retorna só o quadro (sem fechar modal) — usado tanto pelo hx-trigger
    de polling em painel.html (atualização quase em tempo real pra todo mundo
    com a página aberta, não só quem fez a ação) quanto poderia ser reusado
    por um botão de 'atualizar' manual."""
    return render(request, "tarefas/_board.html", {
        "quadro": montar_quadro(request.user, **_filtros_de(request)),
    })


def htmx_badge_pendencias(request: HttpRequest) -> HttpResponse:
    """Fragmento do selo de pendências do menu/card — pollado em base.html
    pra qualquer página (não só o quadro) mostrar a notificação sem precisar
    recarregar. Sem @perm_required: pra um poll de fundo, redirecionar em vez
    de devolver vazio quebraria o swap; a checagem de permissão já está
    embutida em tarefas_pendencias() (retorna {} pra quem não pode ver)."""
    count = tarefas_pendencias(request).get("tarefas_pendentes_count", 0)
    if not count:
        return HttpResponse("")
    return HttpResponse(
        '<span style="background:#dc2626;color:#fff;font-size:.65rem;font-weight:700;'
        'min-width:16px;height:16px;line-height:16px;text-align:center;border-radius:8px;'
        f'padding:0 3px;margin-left:.3rem;">{count}</span>'
    )


@perm_required("tarefas.criar")
def htmx_form_nova_tarefa(request: HttpRequest) -> HttpResponse:
    return render(request, "tarefas/_modal_nova_tarefa.html", {
        "colunas": ColunaStatus.objects.filter(ativa=True),
        "usuarios_atribuiveis": User.objects.filter(is_active=True).order_by("first_name", "username"),
    })


@perm_required("tarefas.criar")
def htmx_criar_tarefa(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()

    titulo = request.POST.get("titulo", "").strip()
    prazo = request.POST.get("prazo", "").strip()
    status_id = request.POST.get("status_id", "").strip()
    responsavel_ids = [int(i) for i in request.POST.getlist("responsaveis") if i.isdigit()]

    if not titulo or not prazo or not status_id or not responsavel_ids:
        messages.error(request, "Preencha título, prazo, status e ao menos um responsável.")
        return _resposta_board(request)

    coluna = get_object_or_404(ColunaStatus, pk=status_id, ativa=True)
    tarefa = Tarefa.objects.create(
        titulo=titulo,
        descricao=request.POST.get("descricao", "").strip(),
        prioridade=request.POST.get("prioridade", "media"),
        prazo=prazo,
        status=coluna,
        criado_por=request.user,
        concluida_em=timezone.now() if coluna.eh_conclusao else None,
    )
    for uid in responsavel_ids:
        TarefaResponsavel.objects.get_or_create(
            tarefa=tarefa, usuario_id=uid, defaults={"adicionado_por": request.user},
        )

    quem = request.user.first_name or request.user.username
    registrar_historico(tarefa, "criacao", "", f"criada por {quem}", request.user)

    messages.success(request, "Tarefa criada.")
    return _resposta_board(request)


def _marcar_visto_e_montar_contexto(request: HttpRequest, tarefa: Tarefa, recem_editada=False) -> dict:
    """Marca a tarefa como vista por request.user (limpa a notificação dela
    pra ele) e monta o contexto do modal de detalhe — usado tanto na abertura
    do card quanto depois de responder na conversa (o modal se re-renderiza
    sem fechar, com a mensagem nova já aparecendo).

    O histórico técnico de alterações (campo mudou de X pra Y) só aparece pra
    Super Admin — pra todo mundo o card mostra só criador/responsáveis,
    descrição e a conversa; quem editou o quê fica registrado, mas não é
    exposto a qualquer responsável."""
    TarefaResponsavel.objects.filter(tarefa=tarefa, usuario=request.user).update(
        visto_em=timezone.now(),
    )
    historico = tarefa.historico.select_related("alterado_por")[:50] if request.user.is_superadmin else None
    return {
        "tarefa": tarefa,
        "pode_editar_conteudo": pode_editar_conteudo(tarefa, request.user),
        "pode_excluir": pode_excluir(tarefa, request.user),
        "recem_editada": recem_editada,
        "usuarios_atribuiveis": User.objects.filter(is_active=True).order_by("first_name", "username"),
        "responsaveis_removiveis": responsaveis_removiveis(tarefa, request.user),
        "comentarios": tarefa.comentarios.select_related("autor"),
        "historico": historico,
    }


@perm_required("tarefas.ver")
def htmx_detalhe_tarefa(request: HttpRequest, pk: int) -> HttpResponse:
    tarefa = _tarefa_visivel_ou_404(request, pk)
    # Calcula ANTES de marcar como visto — é o aviso "isso mudou desde a
    # última vez que você olhou" que precisa aparecer justo agora, na
    # abertura, antes de ser silenciado pela linha abaixo.
    recem_editada = foi_editado_e_nao_visto(tarefa, request.user)
    contexto = _marcar_visto_e_montar_contexto(request, tarefa, recem_editada)
    return render(request, "tarefas/_modal_detalhe.html", contexto)


@perm_required("tarefas.ver")
def htmx_comentar_tarefa(request: HttpRequest, pk: int) -> HttpResponse:
    """Adiciona uma resposta na conversa do card — o "bate-papo" que registra
    como a tarefa foi evoluindo, com nome e horário de quem escreveu. Reabre
    o próprio modal (não fecha pro board) já com a mensagem nova."""
    tarefa = _tarefa_visivel_ou_404(request, pk)
    if not pode_editar_conteudo(tarefa, request.user):
        return HttpResponseForbidden("Só quem criou a tarefa ou é responsável por ela pode responder.")
    if request.method != "POST":
        return HttpResponseForbidden()

    texto = request.POST.get("texto", "").strip()
    if texto:
        TarefaComentario.objects.create(tarefa=tarefa, autor=request.user, texto=texto)
        # Conta como atividade nova pra quem ainda não viu — mesmo sinal que
        # uma edição de conteúdo usa pra acender o selo "Editado"/notificação.
        tarefa.editado_em = timezone.now()
        tarefa.save(update_fields=["editado_em"])
    else:
        messages.error(request, "Escreva algo antes de enviar.")

    contexto = _marcar_visto_e_montar_contexto(request, tarefa)
    return render(request, "tarefas/_modal_detalhe.html", contexto)


@perm_required("tarefas.ver")
def htmx_editar_tarefa(request: HttpRequest, pk: int) -> HttpResponse:
    tarefa = _tarefa_visivel_ou_404(request, pk)
    if not pode_editar_conteudo(tarefa, request.user):
        return HttpResponseForbidden("Só quem criou a tarefa ou é responsável por ela pode editar o conteúdo.")
    if request.method != "POST":
        return HttpResponseForbidden()

    titulo = request.POST.get("titulo", "").strip()
    descricao = request.POST.get("descricao", "").strip()
    prioridade = request.POST.get("prioridade", tarefa.prioridade)
    prazo = request.POST.get("prazo", "").strip()
    responsavel_ids = [int(i) for i in request.POST.getlist("responsaveis") if i.isdigit()]

    if not titulo or not prazo or not responsavel_ids:
        messages.error(request, "Preencha título, prazo e ao menos um responsável.")
        return _resposta_board(request)

    prioridades = dict(Tarefa.PRIORIDADE_CHOICES)
    registrar_historico(tarefa, "titulo", tarefa.titulo, titulo, request.user)
    registrar_historico(tarefa, "descricao", tarefa.descricao, descricao, request.user)
    registrar_historico(
        tarefa, "prioridade",
        prioridades.get(tarefa.prioridade, tarefa.prioridade),
        prioridades.get(prioridade, prioridade),
        request.user,
    )
    registrar_historico(tarefa, "prazo", tarefa.prazo, prazo, request.user)

    tarefa.titulo = titulo
    tarefa.descricao = descricao
    tarefa.prioridade = prioridade
    tarefa.prazo = prazo
    # Avisa quem já tinha visto: card editado depois que a pessoa leu não
    # pode passar batido — vira o selo "Editado" no board dela até reabrir.
    tarefa.editado_em = timezone.now()
    tarefa.save()
    bloqueados = _set_responsaveis(tarefa, responsavel_ids, request.user)
    # Quem editou não precisa de aviso pra si mesmo, mesmo se também for responsável.
    TarefaResponsavel.objects.filter(tarefa=tarefa, usuario=request.user).update(
        visto_em=timezone.now(),
    )

    if bloqueados:
        messages.warning(
            request,
            f"{_nomes(bloqueados)} continua(m) como responsável — só quem "
            "adicionou a pessoa (ou quem criou a tarefa) pode tirá-la.",
        )
    messages.success(request, "Tarefa atualizada.")
    return _resposta_board(request)


@perm_required("tarefas.ver")
def htmx_mover_status(request: HttpRequest, pk: int) -> HttpResponse:
    tarefa = _tarefa_visivel_ou_404(request, pk)
    if not pode_mover_status(tarefa, request.user):
        return HttpResponseForbidden("Você não pode mover esta tarefa.")
    if request.method != "POST":
        return HttpResponseForbidden()

    status_id = request.POST.get("status_id", "").strip()
    coluna = get_object_or_404(ColunaStatus, pk=status_id, ativa=True)

    if coluna.pk != tarefa.status_id:
        registrar_historico(tarefa, "status", tarefa.status.nome, coluna.nome, request.user)
        tarefa.status = coluna
        # Sem reordenação fina dentro da coluna: sempre entra no fim — mantém
        # o drag-and-drop simples (sem precisar calcular índice de soltura).
        tarefa.posicao = Tarefa.objects.filter(status=coluna).exclude(pk=tarefa.pk).count()
        # Marca/zera quando entrou numa coluna de conclusão — é o relógio que o
        # comando arquivar_tarefas_concluidas usa pra tirar do board depois de
        # alguns dias. Voltar pra uma coluna ativa cancela a contagem.
        tarefa.concluida_em = timezone.now() if coluna.eh_conclusao else None
        tarefa.save()

    return _resposta_board(request)


@perm_required("tarefas.ver")
def htmx_arquivar_tarefa(request: HttpRequest, pk: int) -> HttpResponse:
    tarefa = _tarefa_visivel_ou_404(request, pk)
    if not pode_excluir(tarefa, request.user):
        return HttpResponseForbidden("Só quem criou a tarefa (ou o Super Admin) pode excluí-la.")
    if request.method != "POST":
        return HttpResponseForbidden()

    registrar_historico(tarefa, "arquivada", "ativa", "excluída", request.user)
    tarefa.arquivada = True
    tarefa.arquivada_em = timezone.now()
    tarefa.motivo_arquivamento = "excluida"
    tarefa.save()

    messages.success(request, "Tarefa excluída.")
    return _resposta_board(request)
