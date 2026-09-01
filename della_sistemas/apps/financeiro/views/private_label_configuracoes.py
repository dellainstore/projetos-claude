"""Configurações do Private Label: contas, categorias, centros de custo,
contatos, formas de pagamento e regras de recorrência. Uma única rota
(`pl_configuracoes`) com abas internas via `?aba=`; cada cadastro tem seu
próprio par de endpoints HTMX (form + salvar + lista parcial), seguindo o
padrão de modal já usado em `tarefas`."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.decorators import perm_required
from apps.financeiro.models import (
    CategoriaFinanceira,
    CentroCusto,
    ContaBancaria,
    ContatoFinanceiro,
    FormaPagamento,
    NATUREZA_CHOICES,
    RegraRecorrencia,
    FREQUENCIA_CHOICES,
    TIPO_LANCAMENTO_CHOICES,
)
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao
from apps.financeiro.services.private_label.recorrencias import criar_regra_recorrencia
from apps.financeiro.services.private_label.auditoria import registrar_log

ABAS = ["contas", "categorias", "centros-custo", "contatos", "formas-pagamento", "recorrencias"]


def _evento(nome_evento: str) -> HttpResponse:
    """Fecha o modal (corpo vazio no #modal-container, que é sempre o
    hx-target do form) e dispara um evento HTMX que a lista escuta
    (`hx-trigger="<evento> from:body"`) para se auto-atualizar. Evita
    misturar "fechar modal" com "atualizar lista" no mesmo swap."""
    resposta = HttpResponse("")
    resposta["HX-Trigger"] = nome_evento
    return resposta


@perm_required("private_label.configurar")
def pl_configuracoes(request):
    aba = request.GET.get("aba", "contas")
    if aba not in ABAS:
        aba = "contas"
    operacao = obter_operacao_padrao()
    contexto = {"aba": aba, "abas": ABAS}
    if aba == "contas":
        contexto["contas"] = ContaBancaria.objects.filter(operacao=operacao).order_by("nome")
    elif aba == "categorias":
        contexto["categorias"] = CategoriaFinanceira.objects.filter(operacao=operacao).select_related("categoria_pai").order_by("ordem", "nome")
    elif aba == "centros-custo":
        contexto["centros_custo"] = CentroCusto.objects.filter(operacao=operacao).order_by("ordem", "nome")
    elif aba == "contatos":
        contexto["contatos"] = ContatoFinanceiro.objects.filter(operacao=operacao).order_by("nome")
    elif aba == "formas-pagamento":
        contexto["formas_pagamento"] = FormaPagamento.objects.filter(operacao=operacao).order_by("ordem", "nome")
    elif aba == "recorrencias":
        contexto["regras"] = RegraRecorrencia.objects.filter(operacao=operacao).order_by("descricao")
        contexto["categorias_todas"] = CategoriaFinanceira.objects.filter(operacao=operacao, ativa=True).order_by("nome")
        contexto["contas_todas"] = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
        contexto["tipos_lancamento"] = TIPO_LANCAMENTO_CHOICES
        contexto["frequencias"] = FREQUENCIA_CHOICES
    return render(request, "financeiro/private_label/configuracoes.html", contexto)


def _decimal(valor, default="0"):
    try:
        return Decimal(str(valor).replace(",", ".").strip() or default)
    except (InvalidOperation, AttributeError):
        return Decimal(default)


# ── Contas ───────────────────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_conta_form(request, pk=None):
    conta = get_object_or_404(ContaBancaria, pk=pk) if pk else None
    return render(request, "financeiro/private_label/_conta_form.html", {"conta": conta})


@perm_required("private_label.configurar")
def pl_htmx_conta_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_configuracoes")
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    conta = get_object_or_404(ContaBancaria, pk=pk) if pk else ContaBancaria(operacao=operacao, criado_por=request.user)
    nome = request.POST.get("nome", "").strip()
    if not nome:
        return render(request, "financeiro/private_label/_conta_form.html", {"conta": conta, "erro": "Nome é obrigatório."})
    conta.nome = nome
    conta.banco = request.POST.get("banco", "").strip()
    conta.tipo_conta = request.POST.get("tipo_conta", "corrente")
    conta.agencia = request.POST.get("agencia", "").strip()
    conta.conta_mascarada = request.POST.get("conta_mascarada", "").strip()
    conta.cor = request.POST.get("cor", "#c9a96e").strip() or "#c9a96e"
    if not pk:
        conta.saldo_inicial = _decimal(request.POST.get("saldo_inicial"))
        conta.data_saldo_inicial = request.POST.get("data_saldo_inicial") or timezone.localdate()
    conta.ativa = request.POST.get("ativa") == "on"
    conta.incluir_consolidado = request.POST.get("incluir_consolidado") == "on"
    conta.save()
    registrar_log(
        operacao=operacao, entidade="conta_bancaria", objeto_id=conta.id,
        acao="criacao" if not pk else "edicao", usuario=request.user, valor_para=conta.nome,
    )
    return _evento("pl:contas-mudou")


@perm_required("private_label.configurar")
def pl_htmx_contas_lista(request):
    operacao = obter_operacao_padrao()
    contas = ContaBancaria.objects.filter(operacao=operacao).order_by("nome")
    return render(request, "financeiro/private_label/_contas_lista.html", {"contas": contas})


# ── Categorias ───────────────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_categoria_form(request, pk=None):
    operacao = obter_operacao_padrao()
    categoria = get_object_or_404(CategoriaFinanceira, pk=pk) if pk else None
    categorias_pai = CategoriaFinanceira.objects.filter(operacao=operacao, categoria_pai__isnull=True).order_by("nome")
    return render(request, "financeiro/private_label/_categoria_form.html", {
        "categoria": categoria, "categorias_pai": categorias_pai, "naturezas": NATUREZA_CHOICES,
    })


@perm_required("private_label.configurar")
def pl_htmx_categoria_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_configuracoes")
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    categoria = get_object_or_404(CategoriaFinanceira, pk=pk) if pk else CategoriaFinanceira(operacao=operacao)
    nome = request.POST.get("nome", "").strip()
    natureza = request.POST.get("natureza", "")
    if not nome or natureza not in dict(NATUREZA_CHOICES):
        categorias_pai = CategoriaFinanceira.objects.filter(operacao=operacao, categoria_pai__isnull=True).order_by("nome")
        return render(request, "financeiro/private_label/_categoria_form.html", {
            "categoria": categoria, "categorias_pai": categorias_pai, "naturezas": NATUREZA_CHOICES,
            "erro": "Nome e natureza são obrigatórios.",
        })
    categoria.nome = nome
    categoria.natureza = natureza
    pai_id = request.POST.get("categoria_pai") or None
    categoria.categoria_pai_id = pai_id
    categoria.icone = request.POST.get("icone", "").strip()
    categoria.cor = request.POST.get("cor", "#c9a96e").strip() or "#c9a96e"
    categoria.ordem = int(request.POST.get("ordem") or 0)
    categoria.ativa = request.POST.get("ativa") == "on"
    categoria.save()
    registrar_log(
        operacao=operacao, entidade="categoria_financeira", objeto_id=categoria.id,
        acao="criacao" if not pk else "edicao", usuario=request.user, valor_para=categoria.nome,
    )
    return _evento("pl:categorias-mudou")


@perm_required("private_label.configurar")
def pl_htmx_categorias_lista(request):
    operacao = obter_operacao_padrao()
    categorias = CategoriaFinanceira.objects.filter(operacao=operacao).select_related("categoria_pai").order_by("ordem", "nome")
    return render(request, "financeiro/private_label/_categorias_lista.html", {"categorias": categorias})


# ── Centros de custo ─────────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_centro_custo_form(request, pk=None):
    centro = get_object_or_404(CentroCusto, pk=pk) if pk else None
    return render(request, "financeiro/private_label/_centro_custo_form.html", {"centro": centro})


@perm_required("private_label.configurar")
def pl_htmx_centro_custo_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_configuracoes")
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    centro = get_object_or_404(CentroCusto, pk=pk) if pk else CentroCusto(operacao=operacao)
    nome = request.POST.get("nome", "").strip()
    if not nome:
        return render(request, "financeiro/private_label/_centro_custo_form.html", {"centro": centro, "erro": "Nome é obrigatório."})
    centro.nome = nome
    centro.ordem = int(request.POST.get("ordem") or 0)
    centro.ativo = request.POST.get("ativo") == "on"
    centro.save()
    registrar_log(
        operacao=operacao, entidade="centro_custo", objeto_id=centro.id,
        acao="criacao" if not pk else "edicao", usuario=request.user, valor_para=centro.nome,
    )
    return _evento("pl:centros-custo-mudou")


@perm_required("private_label.configurar")
def pl_htmx_centros_custo_lista(request):
    operacao = obter_operacao_padrao()
    centros = CentroCusto.objects.filter(operacao=operacao).order_by("ordem", "nome")
    return render(request, "financeiro/private_label/_centros_custo_lista.html", {"centros_custo": centros})


# ── Contatos ─────────────────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_contato_form(request, pk=None):
    contato = get_object_or_404(ContatoFinanceiro, pk=pk) if pk else None
    return render(request, "financeiro/private_label/_contato_form.html", {"contato": contato})


@perm_required("private_label.configurar")
def pl_htmx_contato_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_configuracoes")
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    contato = get_object_or_404(ContatoFinanceiro, pk=pk) if pk else ContatoFinanceiro(operacao=operacao)
    nome = request.POST.get("nome", "").strip()
    if not nome:
        return render(request, "financeiro/private_label/_contato_form.html", {"contato": contato, "erro": "Nome é obrigatório."})
    contato.nome = nome
    contato.tipo = request.POST.get("tipo", "fornecedor")
    contato.documento = request.POST.get("documento", "").strip()
    contato.telefone = request.POST.get("telefone", "").strip()
    contato.email = request.POST.get("email", "").strip()
    contato.observacoes = request.POST.get("observacoes", "").strip()
    contato.ativo = request.POST.get("ativo") == "on"
    contato.save()
    registrar_log(
        operacao=operacao, entidade="contato_financeiro", objeto_id=contato.id,
        acao="criacao" if not pk else "edicao", usuario=request.user, valor_para=contato.nome,
    )
    return _evento("pl:contatos-mudou")


@perm_required("private_label.configurar")
def pl_htmx_contatos_lista(request):
    operacao = obter_operacao_padrao()
    contatos = ContatoFinanceiro.objects.filter(operacao=operacao).order_by("nome")
    return render(request, "financeiro/private_label/_contatos_lista.html", {"contatos": contatos})


# ── Formas de pagamento ──────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_forma_pagamento_form(request, pk=None):
    forma = get_object_or_404(FormaPagamento, pk=pk) if pk else None
    return render(request, "financeiro/private_label/_forma_pagamento_form.html", {"forma": forma})


@perm_required("private_label.configurar")
def pl_htmx_forma_pagamento_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_configuracoes")
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    forma = get_object_or_404(FormaPagamento, pk=pk) if pk else FormaPagamento(operacao=operacao)
    nome = request.POST.get("nome", "").strip()
    if not nome:
        return render(request, "financeiro/private_label/_forma_pagamento_form.html", {"forma": forma, "erro": "Nome é obrigatório."})
    forma.nome = nome
    forma.ordem = int(request.POST.get("ordem") or 0)
    forma.ativo = request.POST.get("ativo") == "on"
    forma.save()
    registrar_log(
        operacao=operacao, entidade="forma_pagamento", objeto_id=forma.id,
        acao="criacao" if not pk else "edicao", usuario=request.user, valor_para=forma.nome,
    )
    return _evento("pl:formas-pagamento-mudou")


@perm_required("private_label.configurar")
def pl_htmx_formas_pagamento_lista(request):
    operacao = obter_operacao_padrao()
    formas = FormaPagamento.objects.filter(operacao=operacao).order_by("ordem", "nome")
    return render(request, "financeiro/private_label/_formas_pagamento_lista.html", {"formas_pagamento": formas})


# ── Regras de recorrência ────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_recorrencia_form(request):
    operacao = obter_operacao_padrao()
    return render(request, "financeiro/private_label/_recorrencia_form.html", {
        "categorias_todas": CategoriaFinanceira.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "contas_todas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "tipos_lancamento": TIPO_LANCAMENTO_CHOICES,
        "frequencias": FREQUENCIA_CHOICES,
    })


@perm_required("private_label.configurar")
def pl_htmx_recorrencia_salvar(request):
    if request.method != "POST":
        return redirect("financeiro:pl_configuracoes")
    operacao = obter_operacao_padrao()
    descricao = request.POST.get("descricao", "").strip()
    categoria_id = request.POST.get("categoria")
    valor = _decimal(request.POST.get("valor"))
    erro = None
    if not descricao:
        erro = "Descrição é obrigatória."
    elif not categoria_id:
        erro = "Categoria é obrigatória."
    elif valor <= 0:
        erro = "Valor deve ser maior que zero."
    if erro:
        return render(request, "financeiro/private_label/_recorrencia_form.html", {
            "categorias_todas": CategoriaFinanceira.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
            "contas_todas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
            "tipos_lancamento": TIPO_LANCAMENTO_CHOICES, "frequencias": FREQUENCIA_CHOICES, "erro": erro,
        })
    data_final = request.POST.get("data_final") or None
    quantidade = request.POST.get("quantidade_ocorrencias") or None
    criar_regra_recorrencia(
        operacao=operacao, usuario=request.user,
        descricao=descricao, tipo_lancamento=request.POST.get("tipo_lancamento", "despesa"),
        categoria_id=categoria_id, centro_custo_id=request.POST.get("centro_custo") or None,
        conta_prevista_id=request.POST.get("conta_prevista") or None,
        contato_id=request.POST.get("contato") or None, valor=valor,
        frequencia=request.POST.get("frequencia", "mensal"),
        data_inicial=request.POST.get("data_inicial") or timezone.localdate(),
        data_final=data_final, quantidade_ocorrencias=int(quantidade) if quantidade else None,
        janela_meses=int(request.POST.get("janela_meses") or 12),
    )
    return _evento("pl:recorrencias-mudou")


@perm_required("private_label.configurar")
def pl_htmx_recorrencia_pausar(request, pk):
    operacao = obter_operacao_padrao()
    regra = get_object_or_404(RegraRecorrencia, pk=pk, operacao=operacao)
    regra.pausada = not regra.pausada
    regra.save(update_fields=["pausada"])
    registrar_log(
        operacao=operacao, entidade="regra_recorrencia", objeto_id=regra.id,
        acao="edicao", usuario=request.user, campo="pausada", valor_para=regra.pausada,
    )
    regras = RegraRecorrencia.objects.filter(operacao=operacao).order_by("descricao")
    return render(request, "financeiro/private_label/_recorrencias_lista.html", {"regras": regras})


@perm_required("private_label.configurar")
def pl_htmx_recorrencias_lista(request):
    operacao = obter_operacao_padrao()
    regras = RegraRecorrencia.objects.filter(operacao=operacao).order_by("descricao")
    return render(request, "financeiro/private_label/_recorrencias_lista.html", {"regras": regras})
