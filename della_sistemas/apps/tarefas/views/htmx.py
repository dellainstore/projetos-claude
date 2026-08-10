from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.decorators import perm_required
from apps.tarefas.context_processors import tarefas_pendencias
from apps.tarefas.models import ColunaStatus, Tarefa, TarefaResponsavel
from apps.tarefas.services.regras import (
    foi_editado_e_nao_visto,
    montar_quadro,
    pode_editar_conteudo,
    pode_excluir,
    pode_mover_status,
    registrar_historico,
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


def _set_responsaveis(tarefa: Tarefa, ids, usuario) -> None:
    antigos = set(tarefa.responsaveis.values_list("pk", flat=True))
    novos = set(ids)
    if antigos == novos:
        return
    TarefaResponsavel.objects.filter(tarefa=tarefa).exclude(usuario_id__in=novos).delete()
    for uid in novos - antigos:
        TarefaResponsavel.objects.get_or_create(tarefa=tarefa, usuario_id=uid)
    registrar_historico(tarefa, "responsaveis", _nomes(antigos), _nomes(novos), usuario)


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
        TarefaResponsavel.objects.get_or_create(tarefa=tarefa, usuario_id=uid)

    quem = request.user.first_name or request.user.username
    registrar_historico(tarefa, "criacao", "", f"criada por {quem}", request.user)

    messages.success(request, "Tarefa criada.")
    return _resposta_board(request)


@perm_required("tarefas.ver")
def htmx_detalhe_tarefa(request: HttpRequest, pk: int) -> HttpResponse:
    tarefa = _tarefa_visivel_ou_404(request, pk)
    # Calcula ANTES de marcar como visto — é o aviso "isso mudou desde a
    # última vez que você olhou" que precisa aparecer justo agora, na
    # abertura, antes de ser silenciado pela linha abaixo.
    recem_editada = foi_editado_e_nao_visto(tarefa, request.user)

    TarefaResponsavel.objects.filter(tarefa=tarefa, usuario=request.user).update(
        visto_em=timezone.now(),
    )

    return render(request, "tarefas/_modal_detalhe.html", {
        "tarefa": tarefa,
        "pode_editar_conteudo": pode_editar_conteudo(tarefa, request.user),
        "pode_excluir": pode_excluir(tarefa, request.user),
        "recem_editada": recem_editada,
        "usuarios_atribuiveis": User.objects.filter(is_active=True).order_by("first_name", "username"),
        "historico": tarefa.historico.select_related("alterado_por")[:50],
    })


@perm_required("tarefas.ver")
def htmx_editar_tarefa(request: HttpRequest, pk: int) -> HttpResponse:
    tarefa = _tarefa_visivel_ou_404(request, pk)
    if not pode_editar_conteudo(tarefa, request.user):
        return HttpResponseForbidden("Só quem criou a tarefa pode editar o conteúdo dela.")
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
    _set_responsaveis(tarefa, responsavel_ids, request.user)
    # Quem editou não precisa de aviso pra si mesmo, mesmo se também for responsável.
    TarefaResponsavel.objects.filter(tarefa=tarefa, usuario=request.user).update(
        visto_em=timezone.now(),
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
