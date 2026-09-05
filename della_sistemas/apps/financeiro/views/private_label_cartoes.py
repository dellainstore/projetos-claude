"""Cartões de crédito — cadastro, compra parcelada, fatura e pagamento
(Fase 1B, ver plano seções 3/11). Mesmo padrão de modal HTMX das outras
telas do Private Label: form via GET, salvar via POST que devolve um
HX-Trigger consumido pela lista/detalhe."""
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.decorators import perm_required
from apps.financeiro.models import (
    CartaoCredito,
    CategoriaFinanceira,
    CentroCusto,
    CompraCartao,
    ContaBancaria,
    ContatoFinanceiro,
    FaturaCartao,
    FaturaPagamento,
    naturezas_permitidas,
)
from apps.financeiro.services.private_label.cartoes import (
    cancelar_compra_cartao,
    estornar_pagamento_fatura,
    lancar_compra_cartao,
    pagar_fatura,
)
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao


def _evento(nome_evento: str) -> HttpResponse:
    resposta = HttpResponse("")
    resposta["HX-Trigger"] = nome_evento
    return resposta


def _erro_generico(request, mensagem: str) -> HttpResponse:
    return render(request, "financeiro/private_label/_erro_generico_modal.html", {"erro": mensagem})


def _decimal(valor, default="0"):
    try:
        return Decimal(str(valor).replace(",", ".").strip() or default)
    except (InvalidOperation, AttributeError):
        return Decimal(default)


# ── Página principal ────────────────────────────────────────────────────

@perm_required("private_label.ver_cartoes")
def pl_cartoes(request):
    operacao = obter_operacao_padrao()
    cartoes = _cartoes_com_faturas(operacao)
    return render(request, "financeiro/private_label/cartoes.html", {"cartoes": cartoes})


def _cartoes_com_faturas(operacao):
    cartoes = list(CartaoCredito.objects.filter(operacao=operacao).order_by("nome"))
    hoje = timezone.localdate()
    for cartao in cartoes:
        cartao.fatura_atual = (
            FaturaCartao.objects.filter(cartao=cartao, data_vencimento__gte=hoje)
            .order_by("data_vencimento").first()
        )
        cartao.proxima_fatura = None
        if cartao.fatura_atual:
            cartao.proxima_fatura = (
                FaturaCartao.objects.filter(cartao=cartao, data_vencimento__gt=cartao.fatura_atual.data_vencimento)
                .order_by("data_vencimento").first()
            )
    return cartoes


@perm_required("private_label.ver_cartoes")
def pl_htmx_cartoes_lista(request):
    operacao = obter_operacao_padrao()
    cartoes = _cartoes_com_faturas(operacao)
    return render(request, "financeiro/private_label/_cartoes_lista.html", {"cartoes": cartoes})


# ── Cadastro de cartão ──────────────────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_cartao_form(request, pk=None):
    cartao = get_object_or_404(CartaoCredito, pk=pk) if pk else None
    contas = ContaBancaria.objects.filter(operacao=obter_operacao_padrao(), ativa=True).order_by("nome")
    return render(request, "financeiro/private_label/_cartao_form.html", {"cartao": cartao, "contas": contas})


@perm_required("private_label.configurar")
def pl_htmx_cartao_salvar(request):
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    cartao = get_object_or_404(CartaoCredito, pk=pk) if pk else CartaoCredito(operacao=operacao, criado_por=request.user)

    nome = request.POST.get("nome", "").strip()
    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    if not nome:
        return render(request, "financeiro/private_label/_cartao_form.html", {"cartao": cartao, "contas": contas, "erro": "Nome é obrigatório."})

    try:
        dia_fechamento = int(request.POST.get("dia_fechamento") or 0)
        dia_vencimento = int(request.POST.get("dia_vencimento") or 0)
    except ValueError:
        return render(request, "financeiro/private_label/_cartao_form.html", {"cartao": cartao, "contas": contas, "erro": "Dia de fechamento/vencimento inválido."})
    if not (1 <= dia_fechamento <= 28) or not (1 <= dia_vencimento <= 28):
        return render(request, "financeiro/private_label/_cartao_form.html", {"cartao": cartao, "contas": contas, "erro": "Dia de fechamento e vencimento devem estar entre 1 e 28."})

    limite_total = _decimal(request.POST.get("limite_total"))
    if limite_total <= 0:
        return render(request, "financeiro/private_label/_cartao_form.html", {"cartao": cartao, "contas": contas, "erro": "Limite total deve ser maior que zero."})

    cartao.nome = nome
    cartao.banco = request.POST.get("banco", "").strip()
    cartao.final = request.POST.get("final", "").strip()[:4]
    cartao.limite_total = limite_total
    cartao.dia_fechamento = dia_fechamento
    cartao.dia_vencimento = dia_vencimento
    conta_pk = request.POST.get("conta_pagamento_padrao")
    cartao.conta_pagamento_padrao_id = conta_pk or None
    cartao.cor = request.POST.get("cor", "#c9a96e").strip() or "#c9a96e"
    cartao.ativo = request.POST.get("ativo") == "on" if pk else True
    cartao.save()
    return _evento("pl:cartoes-mudou")


# ── Compra parcelada ─────────────────────────────────────────────────────

def _opcoes_compra(operacao):
    return {
        "cartoes": CartaoCredito.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
        # Compra no cartão só sai dinheiro — mesma restrição de natureza que
        # um lançamento tipo "despesa" (ver `naturezas_permitidas`).
        "categorias": CategoriaFinanceira.objects.filter(
            operacao=operacao, ativa=True, natureza__in=naturezas_permitidas("despesa"),
        ).order_by("nome"),
        "centros_custo": CentroCusto.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
        "contatos": ContatoFinanceiro.objects.filter(operacao=operacao, ativo=True).order_by("nome"),
    }


@perm_required("private_label.lancar")
def pl_htmx_compra_cartao_form(request):
    operacao = obter_operacao_padrao()
    return render(request, "financeiro/private_label/_compra_cartao_form.html", _opcoes_compra(operacao))


@perm_required("private_label.lancar")
def pl_htmx_compra_cartao_salvar(request):
    operacao = obter_operacao_padrao()
    opcoes = _opcoes_compra(operacao)

    cartao_pk = request.POST.get("cartao")
    cartao = CartaoCredito.objects.filter(pk=cartao_pk, operacao=operacao).first() if cartao_pk else None
    categoria_pk = request.POST.get("categoria")
    categoria = CategoriaFinanceira.objects.filter(pk=categoria_pk, operacao=operacao).first() if categoria_pk else None
    descricao = request.POST.get("descricao", "").strip()
    valor_total = _decimal(request.POST.get("valor_total"))
    data_compra = request.POST.get("data_compra")

    if not cartao:
        return render(request, "financeiro/private_label/_compra_cartao_form.html", {**opcoes, "erro": "Selecione um cartão."})
    if not categoria or categoria.natureza not in naturezas_permitidas("despesa"):
        return render(request, "financeiro/private_label/_compra_cartao_form.html", {**opcoes, "erro": "Selecione uma categoria de despesa válida."})
    if not descricao:
        return render(request, "financeiro/private_label/_compra_cartao_form.html", {**opcoes, "erro": "Descrição é obrigatória."})
    if valor_total <= 0:
        return render(request, "financeiro/private_label/_compra_cartao_form.html", {**opcoes, "erro": "Valor total deve ser maior que zero."})
    if not data_compra:
        return render(request, "financeiro/private_label/_compra_cartao_form.html", {**opcoes, "erro": "Data da compra é obrigatória."})

    centro_custo_pk = request.POST.get("centro_custo")
    contato_pk = request.POST.get("contato")
    try:
        parcelas_qtd = int(request.POST.get("parcelas_qtd") or 1)
    except ValueError:
        parcelas_qtd = 1

    try:
        lancar_compra_cartao(
            operacao=operacao, cartao=cartao, categoria=categoria, descricao=descricao,
            valor_total=valor_total, data_compra=data_compra, parcelas_qtd=parcelas_qtd,
            centro_custo=CentroCusto.objects.filter(pk=centro_custo_pk).first() if centro_custo_pk else None,
            contato=ContatoFinanceiro.objects.filter(pk=contato_pk).first() if contato_pk else None,
            numero_documento=request.POST.get("numero_documento", "").strip(),
            observacoes=request.POST.get("observacoes", "").strip(),
            usuario=request.user,
        )
    except ValueError as erro:
        return render(request, "financeiro/private_label/_compra_cartao_form.html", {**opcoes, "erro": str(erro)})

    return _evento("pl:cartoes-mudou")


@perm_required("private_label.lancar")
def pl_htmx_compra_cartao_cancelar(request, pk):
    compra = get_object_or_404(CompraCartao, pk=pk)
    if request.method != "POST":
        return _erro_generico(request, "Requisição inválida.")
    try:
        cancelar_compra_cartao(compra, usuario=request.user)
    except ValueError as erro:
        return _erro_generico(request, str(erro))
    return _evento("pl:cartoes-mudou")


# ── Detalhe do cartão (fatura atual/próxima, histórico, compras) ────────

@perm_required("private_label.ver_cartoes")
def pl_cartao_detalhe(request, pk):
    cartao = get_object_or_404(CartaoCredito, pk=pk, operacao=obter_operacao_padrao())
    return render(request, "financeiro/private_label/cartao_detalhe.html", _contexto_detalhe(cartao))


def _contexto_detalhe(cartao):
    hoje = timezone.localdate()
    fatura_atual = (
        FaturaCartao.objects.filter(cartao=cartao, data_vencimento__gte=hoje)
        .order_by("data_vencimento").first()
    )
    proxima_fatura = None
    if fatura_atual:
        proxima_fatura = (
            FaturaCartao.objects.filter(cartao=cartao, data_vencimento__gt=fatura_atual.data_vencimento)
            .order_by("data_vencimento").first()
        )
    historico = FaturaCartao.objects.filter(cartao=cartao).order_by("-competencia_ano", "-competencia_mes")[:12]
    compras_futuras = (
        CompraCartao.objects.filter(cartao=cartao, cancelada=False)
        .prefetch_related("parcelas")
        .order_by("-data_compra")[:30]
    )
    return {
        "cartao": cartao, "fatura_atual": fatura_atual, "proxima_fatura": proxima_fatura,
        "historico": historico, "compras": compras_futuras,
    }


@perm_required("private_label.ver_cartoes")
def pl_htmx_cartao_detalhe_conteudo(request, pk):
    cartao = get_object_or_404(CartaoCredito, pk=pk, operacao=obter_operacao_padrao())
    return render(request, "financeiro/private_label/_cartao_detalhe_conteudo.html", _contexto_detalhe(cartao))


# ── Pagamento de fatura ──────────────────────────────────────────────────

@perm_required("private_label.lancar")
def pl_htmx_fatura_pagar_form(request, pk):
    fatura = get_object_or_404(FaturaCartao, pk=pk)
    contas = ContaBancaria.objects.filter(operacao=obter_operacao_padrao(), ativa=True).order_by("nome")
    return render(request, "financeiro/private_label/_fatura_pagar_form.html", {"fatura": fatura, "contas": contas})


@perm_required("private_label.lancar")
def pl_htmx_fatura_pagar_salvar(request, pk):
    fatura = get_object_or_404(FaturaCartao, pk=pk)
    contas = ContaBancaria.objects.filter(operacao=obter_operacao_padrao(), ativa=True).order_by("nome")

    conta_pk = request.POST.get("conta")
    conta = ContaBancaria.objects.filter(pk=conta_pk).first() if conta_pk else None
    valor = _decimal(request.POST.get("valor"))
    data = request.POST.get("data")

    if not conta:
        return render(request, "financeiro/private_label/_fatura_pagar_form.html", {"fatura": fatura, "contas": contas, "erro": "Selecione a conta de pagamento."})
    if not data:
        return render(request, "financeiro/private_label/_fatura_pagar_form.html", {"fatura": fatura, "contas": contas, "erro": "Informe a data do pagamento."})

    try:
        pagar_fatura(
            fatura=fatura, valor=valor, data=data, conta=conta,
            observacao=request.POST.get("observacao", "").strip(), usuario=request.user,
        )
    except ValueError as erro:
        return render(request, "financeiro/private_label/_fatura_pagar_form.html", {"fatura": fatura, "contas": contas, "erro": str(erro)})

    return _evento("pl:cartoes-mudou")


@perm_required("private_label.lancar")
def pl_htmx_fatura_pagamento_estornar(request, pk):
    pagamento = get_object_or_404(FaturaPagamento, pk=pk)
    if request.method != "POST":
        return _erro_generico(request, "Requisição inválida.")
    try:
        estornar_pagamento_fatura(pagamento, usuario=request.user, motivo="estornado pela tela")
    except ValueError as erro:
        return _erro_generico(request, str(erro))
    return _evento("pl:cartoes-mudou")
