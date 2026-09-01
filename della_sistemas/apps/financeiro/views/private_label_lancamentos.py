"""Tela central de Lançamentos do Private Label. A listagem opera no nível
de PARCELA (não de lançamento) — cada linha é uma parcela, com o número
X/Y mostrado quando o lançamento tem mais de uma. Isso mantém baixa e
seleção múltipla num caminho de código só, parcelado ou não (mesma decisão
de design dos models — ver `Parcela`)."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import models
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.decorators import perm_required
from apps.financeiro.models import (
    AnexoFinanceiro,
    Baixa,
    CategoriaFinanceira,
    CentroCusto,
    ContaBancaria,
    ContatoFinanceiro,
    ESTADO_CANCELADO,
    FormaPagamento,
    LancamentoFinanceiro,
    LogAuditoriaFinanceiro,
    Parcela,
    TIPO_LANCAMENTO_CHOICES,
    TagFinanceira,
    Transferencia,
    naturezas_permitidas,
)
from apps.financeiro.services.private_label.ajustes import ajustar_saldo
from apps.financeiro.services.private_label.auditoria import registrar_log
from apps.financeiro.services.private_label.baixas import dar_baixa, dar_baixa_em_lote, estornar_baixa
from apps.financeiro.services.private_label.lancamentos import (
    cancelar_lancamento,
    criar_lancamento,
    deletar_lancamento,
    duplicar_lancamento,
    editar_lancamento,
    editar_parcela,
    reparcelar,
    reparcelar_mantendo_parcelas,
)
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao
from apps.financeiro.services.private_label.recorrencias import verificar_lazy
from apps.financeiro.services.private_label.transferencias import estornar_transferencia, transferir


def _evento(nome_evento: str) -> HttpResponse:
    resposta = HttpResponse("")
    resposta["HX-Trigger"] = nome_evento
    return resposta


def _decimal(valor, default="0"):
    try:
        return Decimal(str(valor).replace(",", ".").strip() or default)
    except (InvalidOperation, AttributeError):
        return Decimal(default)


def pl_home(request):
    if request.user.pode_ver_private_label_dashboard:
        return redirect("financeiro:pl_dashboard")
    if request.user.pode_ver_private_label_lancamentos:
        return redirect("financeiro:pl_lancamentos")
    if request.user.pode_configurar_private_label:
        return redirect("financeiro:pl_configuracoes")
    messages.error(request, "Você não tem acesso ao módulo Private Label.")
    return redirect("core:home")


def _opcoes_cadastro(operacao):
    return {
        "categorias": CategoriaFinanceira.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "centros_custo": CentroCusto.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
        "contas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "contatos": ContatoFinanceiro.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
        "formas_pagamento": FormaPagamento.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
        "tipos_lancamento": TIPO_LANCAMENTO_CHOICES,
    }


def _parcelas_filtradas(request, operacao):
    qs = Parcela.objects.filter(lancamento__operacao=operacao).select_related(
        "lancamento", "lancamento__categoria", "lancamento__contato",
        "lancamento__centro_custo", "lancamento__conta_prevista", "conta_prevista",
    ).prefetch_related("baixas")

    tipo = request.GET.get("tipo")
    if tipo:
        qs = qs.filter(lancamento__tipo=tipo)
    categoria = request.GET.get("categoria")
    if categoria:
        qs = qs.filter(lancamento__categoria_id=categoria)
    centro_custo = request.GET.get("centro_custo")
    if centro_custo:
        qs = qs.filter(lancamento__centro_custo_id=centro_custo)
    conta = request.GET.get("conta")
    if conta:
        # Conta EFETIVA da parcela: a dela própria se tiver, senão a do
        # lançamento (mesma regra de `conta_prevista_efetiva`) — filtrar só
        # por `lancamento__conta_prevista_id` ignorava o override por
        # parcela e misturava contas diferentes no mesmo lançamento.
        qs = qs.filter(
            models.Q(conta_prevista_id=conta)
            | models.Q(conta_prevista_id__isnull=True, lancamento__conta_prevista_id=conta)
        )
    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(lancamento__descricao__icontains=busca)
    data_de = request.GET.get("data_de")
    if data_de:
        qs = qs.filter(data_vencimento__gte=data_de)
    data_ate = request.GET.get("data_ate")
    if data_ate:
        qs = qs.filter(data_vencimento__lte=data_ate)

    situacao = request.GET.get("situacao")
    hoje = timezone.localdate()
    if situacao == "vencido":
        qs = qs.filter(estado_estrutural__in=["aberto", "parcial"], data_vencimento__lt=hoje)
    elif situacao == "aberto":
        qs = qs.filter(estado_estrutural="aberto")
    elif situacao == "parcial":
        qs = qs.filter(estado_estrutural="parcial")
    elif situacao == "quitado":
        qs = qs.filter(estado_estrutural="quitado")
    elif situacao == "cancelado":
        qs = qs.filter(estado_estrutural="cancelado")
    else:
        # padrão: esconde canceladas (ruído) a menos que peçam explicitamente
        qs = qs.exclude(estado_estrutural="cancelado")

    return qs.order_by("data_vencimento", "lancamento_id", "numero")


def _transferencias_filtradas(request, operacao):
    """Transferências não são LancamentoFinanceiro (nunca entram em
    receita/despesa/DRE — ver plano), mas o usuário precisa VER que
    aconteceram na tela de Lançamentos, senão "some" sem deixar rastro
    visível. Mesclada na listagem como linha própria (kind="transferencia"),
    sem contar nos totais de gasto/recebido."""
    tipo = request.GET.get("tipo")
    if tipo and tipo != "transferencia":
        return Transferencia.objects.none()

    situacao = request.GET.get("situacao", "")
    if situacao in ("vencido", "aberto", "parcial"):
        # esses estados não existem pra transferência (é sempre imediata)
        return Transferencia.objects.none()

    qs = Transferencia.objects.filter(operacao=operacao).select_related("conta_origem", "conta_destino")
    qs = qs.filter(estornada=(situacao == "cancelado"))

    conta = request.GET.get("conta")
    if conta:
        qs = qs.filter(models.Q(conta_origem_id=conta) | models.Q(conta_destino_id=conta))
    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(observacao__icontains=busca)
    data_de = request.GET.get("data_de")
    if data_de:
        qs = qs.filter(data__gte=data_de)
    data_ate = request.GET.get("data_ate")
    if data_ate:
        qs = qs.filter(data__lte=data_ate)
    return qs.order_by("data")


def _linhas_lancamentos(request, operacao):
    """Lista unificada e ordenada por data: parcelas de LancamentoFinanceiro
    + Transferências, cada uma como uma linha com `kind` próprio pro
    template distinguir. Corta em 300 linhas no total (não 300+300)."""
    linhas = [
        {"kind": "lancamento", "data": p.data_vencimento, "parcela": p}
        for p in _parcelas_filtradas(request, operacao)
    ]
    linhas += [
        {"kind": "transferencia", "data": t.data, "transferencia": t}
        for t in _transferencias_filtradas(request, operacao)
    ]
    linhas.sort(key=lambda linha: linha["data"])
    return linhas[:300]


@perm_required("private_label.ver_lancamentos")
def pl_lancamentos(request):
    verificar_lazy()
    operacao = obter_operacao_padrao()
    contexto = {
        "linhas": _linhas_lancamentos(request, operacao),
        "querystring": request.GET.urlencode(),
        **_opcoes_cadastro(operacao),
    }
    return render(request, "financeiro/private_label/lancamentos.html", contexto)


@perm_required("private_label.ver_lancamentos")
def pl_htmx_lancamentos_lista(request):
    operacao = obter_operacao_padrao()
    return render(request, "financeiro/private_label/_lancamentos_lista.html", {
        "linhas": _linhas_lancamentos(request, operacao),
    })


# ── Novo / editar lançamento ─────────────────────────────────────────────

def _pode_editar_lancamento(user, lancamento) -> bool:
    """Quem criou o lançamento pode editá-lo; superadmin pode editar
    qualquer um. Deletar (definitivo) é só superadmin — ver
    `pl_htmx_lancamento_deletar`."""
    return user.is_superadmin or lancamento.criado_por_id == user.id


def _contexto_edicao(lancamento, parcela_pk=None):
    """Monta o contexto extra do modo edição: qual parcela está no foco
    (pra "editar só esta parcela") e se a série já tem baixa em algum
    lugar (trava a opção "reparcelar tudo")."""
    parcela = None
    if parcela_pk:
        parcela = lancamento.parcelas.filter(pk=parcela_pk).first()
    if parcela is None:
        parcela = lancamento.parcelas.order_by("numero").first()
    return {
        "parcela": parcela,
        "lancamento_tem_baixa": Baixa.objects.filter(parcela__lancamento=lancamento).exists(),
    }


@perm_required("private_label.lancar")
def pl_htmx_lancamento_form(request, pk=None):
    operacao = obter_operacao_padrao()
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao) if pk else None
    if lancamento and not _pode_editar_lancamento(request.user, lancamento):
        return render(request, "financeiro/private_label/_erro_generico_modal.html", {
            "erro": "Você só pode editar lançamentos que você mesmo criou (ou ser superadmin).",
        })
    contexto = {"lancamento": lancamento, **_opcoes_cadastro(operacao)}
    if lancamento:
        contexto["tags_atuais"] = ", ".join(lancamento.tags.values_list("nome", flat=True))
        contexto.update(_contexto_edicao(lancamento, request.GET.get("parcela")))
    return render(request, "financeiro/private_label/_lancamento_form.html", contexto)


@perm_required("private_label.lancar")
def pl_htmx_lancamento_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_lancamentos")
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")

    if pk:
        lancamento_existente = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao)
        if not _pode_editar_lancamento(request.user, lancamento_existente):
            return render(request, "financeiro/private_label/_erro_generico_modal.html", {
                "erro": "Você só pode editar lançamentos que você mesmo criou (ou ser superadmin).",
            })
        if request.POST.get("tipo") != lancamento_existente.tipo and not request.user.is_superadmin:
            return render(request, "financeiro/private_label/_erro_generico_modal.html", {
                "erro": "Só o superadmin pode trocar entre despesa e receita.",
            })

    tipo = request.POST.get("tipo", "despesa")
    categoria_id = request.POST.get("categoria")
    categoria = CategoriaFinanceira.objects.filter(pk=categoria_id, operacao=operacao).first() if categoria_id else None
    descricao = request.POST.get("descricao", "").strip()
    contato = ContatoFinanceiro.objects.filter(pk=request.POST.get("contato"), operacao=operacao).first() if request.POST.get("contato") else None
    centro_custo = CentroCusto.objects.filter(pk=request.POST.get("centro_custo"), operacao=operacao).first() if request.POST.get("centro_custo") else None
    conta_prevista = ContaBancaria.objects.filter(pk=request.POST.get("conta_prevista"), operacao=operacao).first() if request.POST.get("conta_prevista") else None
    forma_pagamento = FormaPagamento.objects.filter(pk=request.POST.get("forma_pagamento"), operacao=operacao).first() if request.POST.get("forma_pagamento") else None
    tags_texto = request.POST.get("tags", "").strip()
    tags = []
    if tags_texto:
        for nome in {t.strip() for t in tags_texto.split(",") if t.strip()}:
            tag, _ = TagFinanceira.objects.get_or_create(operacao=operacao, nome=nome)
            tags.append(tag)

    erro = None
    if not descricao:
        erro = "Descrição é obrigatória."
    elif not categoria:
        erro = "Categoria é obrigatória."
    elif not pk and _decimal(request.POST.get("valor_original")) <= 0:
        erro = "Valor deve ser maior que zero."
    elif categoria.natureza not in naturezas_permitidas(tipo):
        # nunca confia só no filtro do <select> feito em JS — revalida aqui
        erro = f"A categoria \"{categoria.nome}\" não é compatível com {'despesa' if tipo == 'despesa' else 'receita'}."

    def _erro_com_contexto(lancamento, mensagem):
        contexto = {"lancamento": lancamento, "erro": mensagem, **_opcoes_cadastro(operacao)}
        if lancamento:
            contexto.update(_contexto_edicao(lancamento, request.POST.get("parcela_pk")))
        return render(request, "financeiro/private_label/_lancamento_form.html", contexto)

    if erro:
        lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao) if pk else None
        return _erro_com_contexto(lancamento, erro)

    if pk:
        lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao)
        try:
            editar_lancamento(
                lancamento, usuario=request.user, tags=tags, descricao=descricao, contato=contato,
                categoria=categoria, centro_custo=centro_custo, conta_prevista=conta_prevista,
                forma_pagamento=forma_pagamento, numero_documento=request.POST.get("numero_documento", "").strip(),
                observacoes=request.POST.get("observacoes", "").strip(), tipo=tipo,
            )
        except ValueError as e:
            return _erro_com_contexto(lancamento, str(e))
        # Corrigir o valor de UMA parcela só, ou reparcelar a série inteira
        # (só quando nenhuma parcela tem baixa ainda) — nunca as duas coisas
        # ao mesmo tempo. Superadmin pode mudar valor mesmo com baixa.
        escopo_valor = request.POST.get("escopo_valor", "parcela")
        lancamento_tem_baixa = Baixa.objects.filter(parcela__lancamento=lancamento).exists()
        try:
            if escopo_valor == "todas" and lancamento_tem_baixa:
                # Já tem baixa em algum lugar da série — apagar e recriar
                # parcelas (reparcelar()) esbarraria em Baixa.parcela=PROTECT.
                # Só superadmin corrige o total mantendo as parcelas como
                # estão (nada é apagado).
                if not request.user.is_superadmin:
                    raise ValueError("Só o superadmin pode reparcelar uma série que já tem baixa.")
                reparcelar_mantendo_parcelas(
                    lancamento, usuario=request.user,
                    novo_valor_total=_decimal(request.POST.get("novo_valor_total")),
                    ignorar_baixa=True,
                )
            elif escopo_valor == "todas":
                reparcelar(
                    lancamento, usuario=request.user,
                    novo_valor_total=_decimal(request.POST.get("novo_valor_total")),
                    novas_parcelas_qtd=int(request.POST.get("novas_parcelas_qtd") or 1),
                    primeiro_vencimento=request.POST.get("novo_primeiro_vencimento") or None,
                    frequencia_parcelas=request.POST.get("nova_frequencia_parcelas", "mensal"),
                )
            else:
                parcela_pk = request.POST.get("parcela_pk")
                if parcela_pk:
                    parcela = get_object_or_404(Parcela, pk=parcela_pk, lancamento=lancamento)
                    novo_valor = request.POST.get("parcela_valor")
                    # Conta prevista é por parcela — "manter" quando o campo
                    # nem veio no POST (form antigo em cache), senão aplica o
                    # que veio (inclusive vazio = limpar, cai no fallback do
                    # lançamento). Nunca mexe na conta das OUTRAS parcelas.
                    if "parcela_conta_prevista" in request.POST:
                        conta_parcela_id = request.POST.get("parcela_conta_prevista")
                        nova_conta_parcela = (
                            ContaBancaria.objects.filter(pk=conta_parcela_id, operacao=operacao).first()
                            if conta_parcela_id else None
                        )
                    else:
                        nova_conta_parcela = "__manter__"
                    editar_parcela(
                        parcela, usuario=request.user,
                        valor=novo_valor if novo_valor else None,
                        ignorar_baixa=request.user.is_superadmin,
                        data_vencimento=request.POST.get("parcela_vencimento") or None,
                        conta_prevista=nova_conta_parcela,
                    )
        except ValueError as e:
            return _erro_com_contexto(lancamento, str(e))
    else:
        parcelas_qtd = int(request.POST.get("parcelas_qtd") or 1)
        # Um campo de data só no formulário (menos confuso pro usuário) —
        # a "competência" (usada no DRE por regime de competência, Fase 1C)
        # é sempre igual à data informada. Continuam sendo 2 campos no
        # model porque servem a propósitos diferentes lá na frente, mas
        # aqui na criação simples viram a mesma coisa.
        data_informada = request.POST.get("data_vencimento") or timezone.localdate()
        criar_lancamento(
            operacao=operacao, tipo=tipo, descricao=descricao,
            valor_original=_decimal(request.POST.get("valor_original")), data_competencia=data_informada,
            primeiro_vencimento=data_informada,
            categoria=categoria, contato=contato, centro_custo=centro_custo, conta_prevista=conta_prevista,
            forma_pagamento=forma_pagamento, numero_documento=request.POST.get("numero_documento", "").strip(),
            observacoes=request.POST.get("observacoes", "").strip(), tags=tags,
            parcelas_qtd=parcelas_qtd, frequencia_parcelas=request.POST.get("frequencia_parcelas", "mensal"),
            usuario=request.user,
        )
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_lancamento_duplicar(request, pk):
    operacao = obter_operacao_padrao()
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao)
    duplicar_lancamento(lancamento, usuario=request.user)
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_lancamento_cancelar(request, pk):
    operacao = obter_operacao_padrao()
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao)
    try:
        cancelar_lancamento(lancamento, usuario=request.user)
    except ValueError as e:
        messages.error(request, str(e))
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_lancamento_deletar(request, pk):
    """Exclusão definitiva — só superadmin, e só quando o lançamento nunca
    teve baixa (ver `deletar_lancamento`). "Cancelar" continua sendo a via
    normal (lógica, preserva histórico) para quem criou."""
    operacao = obter_operacao_padrao()
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao)
    if not request.user.is_superadmin:
        return render(request, "financeiro/private_label/_erro_generico_modal.html", {
            "erro": "Só o superadmin pode excluir definitivamente um lançamento.",
        })
    try:
        deletar_lancamento(lancamento, usuario=request.user)
    except ValueError as e:
        return render(request, "financeiro/private_label/_erro_generico_modal.html", {"erro": str(e)})
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.ver_lancamentos")
def pl_htmx_lancamento_detalhe(request, pk):
    operacao = obter_operacao_padrao()
    lancamento = get_object_or_404(
        LancamentoFinanceiro.objects.prefetch_related("parcelas__baixas", "anexos", "tags"),
        pk=pk, operacao=operacao,
    )
    logs = LogAuditoriaFinanceiro.objects.filter(
        operacao=operacao, entidade="lancamento", objeto_id=lancamento.id,
    ).order_by("-criado_em")[:30]
    return render(request, "financeiro/private_label/_lancamento_detalhe.html", {
        "lancamento": lancamento, "logs": logs,
    })


# ── Anexos ───────────────────────────────────────────────────────────────

@perm_required("private_label.lancar")
def pl_htmx_anexo_upload(request, pk):
    operacao = obter_operacao_padrao()
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk, operacao=operacao)
    arquivo = request.FILES.get("arquivo")
    if arquivo:
        extensao = arquivo.name.rsplit(".", 1)[-1].lower() if "." in arquivo.name else ""
        if extensao not in AnexoFinanceiro.EXTENSOES_PERMITIDAS:
            messages.error(request, f"Extensão .{extensao} não permitida.")
        elif arquivo.size > AnexoFinanceiro.TAMANHO_MAXIMO_MB * 1024 * 1024:
            messages.error(request, f"Arquivo maior que {AnexoFinanceiro.TAMANHO_MAXIMO_MB}MB.")
        else:
            AnexoFinanceiro.objects.create(
                lancamento=lancamento, arquivo=arquivo, nome_original=arquivo.name,
                tamanho=arquivo.size, tipo_mime=arquivo.content_type or "", enviado_por=request.user,
            )
            registrar_log(
                operacao=operacao, entidade="lancamento", objeto_id=lancamento.id,
                acao="edicao", usuario=request.user, campo="anexo", valor_para=arquivo.name,
            )
    logs = LogAuditoriaFinanceiro.objects.filter(
        operacao=operacao, entidade="lancamento", objeto_id=lancamento.id,
    ).order_by("-criado_em")[:30]
    return render(request, "financeiro/private_label/_lancamento_detalhe.html", {"lancamento": lancamento, "logs": logs})


@perm_required("private_label.ver_lancamentos")
def pl_anexo_download(request, pk):
    """Único jeito de baixar um anexo — nunca servido como mídia pública
    (ver plano, seção 15). Valida permissão + vínculo + existência em disco
    antes de servir."""
    operacao = obter_operacao_padrao()
    anexo = get_object_or_404(AnexoFinanceiro, pk=pk, lancamento__operacao=operacao)
    if not request.user.tem_perm("private_label.ver_lancamentos"):
        return HttpResponseForbidden("Sem permissão.")
    if not anexo.arquivo or not anexo.arquivo.storage.exists(anexo.arquivo.name):
        from django.http import Http404
        raise Http404("Arquivo não encontrado.")
    from django.http import FileResponse
    resposta = FileResponse(anexo.arquivo.open("rb"), as_attachment=True, filename=anexo.nome_original)
    return resposta


# ── Baixas ───────────────────────────────────────────────────────────────

@perm_required("private_label.lancar")
def pl_htmx_baixa_form(request, pk):
    operacao = obter_operacao_padrao()
    parcela = get_object_or_404(Parcela, pk=pk, lancamento__operacao=operacao)
    contexto = {
        "parcela": parcela,
        "contas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "formas_pagamento": FormaPagamento.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
    }
    return render(request, "financeiro/private_label/_baixa_form.html", contexto)


@perm_required("private_label.lancar")
def pl_htmx_baixa_salvar(request, pk):
    if request.method != "POST":
        return redirect("financeiro:pl_lancamentos")
    operacao = obter_operacao_padrao()
    parcela = get_object_or_404(Parcela, pk=pk, lancamento__operacao=operacao)
    conta = get_object_or_404(ContaBancaria, pk=request.POST.get("conta"), operacao=operacao)
    forma_pagamento_id = request.POST.get("forma_pagamento") or None
    forma_pagamento = FormaPagamento.objects.filter(pk=forma_pagamento_id, operacao=operacao).first() if forma_pagamento_id else None
    permitir_excedente = request.user.tem_perm("private_label.baixar_valor_maior") and request.POST.get("permitir_excedente") == "on"
    try:
        dar_baixa(
            parcela=parcela, valor_principal=_decimal(request.POST.get("valor_principal")),
            data=request.POST.get("data") or timezone.localdate(), conta=conta, forma_pagamento=forma_pagamento,
            juros=_decimal(request.POST.get("juros")), multa=_decimal(request.POST.get("multa")),
            desconto=_decimal(request.POST.get("desconto")), observacao=request.POST.get("observacao", "").strip(),
            usuario=request.user, permitir_excedente=permitir_excedente,
        )
    except ValueError as e:
        contexto = {
            "parcela": parcela, "erro": str(e),
            "contas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
            "formas_pagamento": FormaPagamento.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
        }
        return render(request, "financeiro/private_label/_baixa_form.html", contexto)
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_baixa_estornar(request, pk):
    operacao = obter_operacao_padrao()
    baixa = get_object_or_404(Baixa, pk=pk, parcela__lancamento__operacao=operacao)
    try:
        estornar_baixa(baixa, usuario=request.user, motivo=request.POST.get("motivo", "Estorno manual"))
    except ValueError as e:
        messages.error(request, str(e))
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_baixa_lote(request):
    if request.method != "POST":
        return redirect("financeiro:pl_lancamentos")
    operacao = obter_operacao_padrao()
    ids = [int(i) for i in request.POST.getlist("parcela_ids") if i.isdigit()]
    parcelas = Parcela.objects.filter(pk__in=ids, lancamento__operacao=operacao)
    conta = get_object_or_404(ContaBancaria, pk=request.POST.get("conta"), operacao=operacao)
    forma_pagamento_id = request.POST.get("forma_pagamento") or None
    forma_pagamento = FormaPagamento.objects.filter(pk=forma_pagamento_id, operacao=operacao).first() if forma_pagamento_id else None
    dar_baixa_em_lote(
        parcelas, data=request.POST.get("data") or timezone.localdate(), conta=conta,
        forma_pagamento=forma_pagamento, usuario=request.user,
    )
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_baixa_lote_form(request):
    ids = request.GET.get("ids", "")
    ids_lista = [i for i in ids.split(",") if i.isdigit()]
    operacao = obter_operacao_padrao()
    contexto = {
        "ids_lista": ids_lista,
        "quantidade": len(ids_lista),
        "contas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "formas_pagamento": FormaPagamento.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
    }
    return render(request, "financeiro/private_label/_baixa_lote_form.html", contexto)


# ── Transferências ───────────────────────────────────────────────────────

@perm_required("private_label.lancar")
def pl_htmx_transferencia_form(request):
    operacao = obter_operacao_padrao()
    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    return render(request, "financeiro/private_label/_transferencia_form.html", {"contas": contas})


@perm_required("private_label.lancar")
def pl_htmx_transferencia_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_lancamentos")
    operacao = obter_operacao_padrao()
    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    try:
        origem = get_object_or_404(ContaBancaria, pk=request.POST.get("conta_origem"), operacao=operacao)
        destino = get_object_or_404(ContaBancaria, pk=request.POST.get("conta_destino"), operacao=operacao)
        transferir(
            operacao=operacao, conta_origem=origem, conta_destino=destino,
            valor=_decimal(request.POST.get("valor")), data=request.POST.get("data") or timezone.localdate(),
            observacao=request.POST.get("observacao", "").strip(), usuario=request.user,
        )
    except ValueError as e:
        return render(request, "financeiro/private_label/_transferencia_form.html", {"contas": contas, "erro": str(e)})
    return _evento("pl:lancamentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_transferencia_estornar(request, pk):
    operacao = obter_operacao_padrao()
    transferencia = get_object_or_404(Transferencia, pk=pk, operacao=operacao)
    try:
        estornar_transferencia(transferencia, usuario=request.user, motivo=request.POST.get("motivo", "Estorno manual"))
    except ValueError as e:
        messages.error(request, str(e))
    return _evento("pl:lancamentos-mudou")


# ── Ajuste de saldo ──────────────────────────────────────────────────────

@perm_required("private_label.ajustar_saldo")
def pl_htmx_ajuste_saldo_form(request):
    operacao = obter_operacao_padrao()
    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    return render(request, "financeiro/private_label/_ajuste_saldo_form.html", {"contas": contas})


@perm_required("private_label.ajustar_saldo")
def pl_htmx_ajuste_saldo_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_lancamentos")
    operacao = obter_operacao_padrao()
    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    try:
        conta = get_object_or_404(ContaBancaria, pk=request.POST.get("conta"), operacao=operacao)
        ajustar_saldo(
            operacao=operacao, conta=conta, valor=_decimal(request.POST.get("valor")),
            motivo=request.POST.get("motivo", ""), usuario=request.user,
        )
    except ValueError as e:
        return render(request, "financeiro/private_label/_ajuste_saldo_form.html", {"contas": contas, "erro": str(e)})
    return _evento("pl:lancamentos-mudou")
