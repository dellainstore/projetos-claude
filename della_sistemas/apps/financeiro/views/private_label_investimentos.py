"""Investimentos (Fase 2) — cadastro de conta de investimento + aplicação/
resgate/rendimento/taxa, ver `services/private_label/investimentos.py`."""
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.core.decorators import perm_required
from apps.financeiro.models import (
    CategoriaFinanceira,
    ContaBancaria,
    ContaInvestimento,
    InvestimentoTransacao,
    TIPO_PRODUTO_INVESTIMENTO_CHOICES,
)
from apps.financeiro.services.private_label.investimentos import (
    aplicar,
    estornar_transacao,
    registrar_rendimento,
    registrar_taxa,
    resgatar,
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


@perm_required("private_label.ver_investimentos")
def pl_investimentos(request):
    operacao = obter_operacao_padrao()
    return render(request, "financeiro/private_label/investimentos.html", _contexto_lista(operacao))


def _contexto_lista(operacao):
    contas = list(ContaInvestimento.objects.filter(operacao=operacao).order_by("nome"))
    for conta in contas:
        conta.saldo = conta.saldo_atual()
    transacoes = (
        InvestimentoTransacao.objects.filter(operacao=operacao)
        .select_related("conta_investimento", "conta_bancaria", "categoria")
        .order_by("-data", "-id")[:50]
    )
    return {"contas": contas, "transacoes": transacoes}


@perm_required("private_label.ver_investimentos")
def pl_htmx_investimentos_lista(request):
    operacao = obter_operacao_padrao()
    return render(request, "financeiro/private_label/_investimentos_lista.html", _contexto_lista(operacao))


# ── Cadastro de conta de investimento ────────────────────────────────────

@perm_required("private_label.configurar")
def pl_htmx_conta_investimento_form(request, pk=None):
    conta = get_object_or_404(ContaInvestimento, pk=pk) if pk else None
    return render(request, "financeiro/private_label/_conta_investimento_form.html", {
        "conta": conta, "tipos_produto": TIPO_PRODUTO_INVESTIMENTO_CHOICES,
    })


@perm_required("private_label.configurar")
def pl_htmx_conta_investimento_salvar(request):
    operacao = obter_operacao_padrao()
    pk = request.POST.get("pk")
    conta = get_object_or_404(ContaInvestimento, pk=pk) if pk else ContaInvestimento(operacao=operacao, criado_por=request.user)

    nome = request.POST.get("nome", "").strip()
    contexto_erro = {"conta": conta, "tipos_produto": TIPO_PRODUTO_INVESTIMENTO_CHOICES}
    if not nome:
        return render(request, "financeiro/private_label/_conta_investimento_form.html", {**contexto_erro, "erro": "Nome é obrigatório."})

    conta.nome = nome
    conta.instituicao = request.POST.get("instituicao", "").strip()
    conta.tipo_produto = request.POST.get("tipo_produto", "outro")
    conta.ativa = request.POST.get("ativa") == "on" if pk else True
    conta.save()
    return _evento("pl:investimentos-mudou")


# ── Transações (aplicar/resgatar/rendimento/taxa) ────────────────────────

def _opcoes_transacao(operacao):
    return {
        "contas_investimento": ContaInvestimento.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "contas_bancarias": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "categorias_receita_financeira": CategoriaFinanceira.objects.filter(
            operacao=operacao, ativa=True, natureza="receita_financeira",
        ).order_by("nome"),
        "categorias_despesa_financeira": CategoriaFinanceira.objects.filter(
            operacao=operacao, ativa=True, natureza="despesa_financeira",
        ).order_by("nome"),
    }


@perm_required("private_label.lancar")
def pl_htmx_investimento_transacao_form(request):
    operacao = obter_operacao_padrao()
    tipo = request.GET.get("tipo", "aplicacao")
    return render(request, "financeiro/private_label/_investimento_transacao_form.html", {
        **_opcoes_transacao(operacao), "tipo": tipo,
    })


@perm_required("private_label.lancar")
def pl_htmx_investimento_transacao_salvar(request):
    operacao = obter_operacao_padrao()
    opcoes = _opcoes_transacao(operacao)
    tipo = request.POST.get("tipo", "aplicacao")

    conta_investimento_pk = request.POST.get("conta_investimento")
    conta_investimento = ContaInvestimento.objects.filter(pk=conta_investimento_pk, operacao=operacao).first() if conta_investimento_pk else None
    valor = _decimal(request.POST.get("valor"))
    data = request.POST.get("data")

    if not conta_investimento:
        return render(request, "financeiro/private_label/_investimento_transacao_form.html", {**opcoes, "tipo": tipo, "erro": "Selecione a conta de investimento."})
    if valor <= 0:
        return render(request, "financeiro/private_label/_investimento_transacao_form.html", {**opcoes, "tipo": tipo, "erro": "Valor deve ser maior que zero."})
    if not data:
        return render(request, "financeiro/private_label/_investimento_transacao_form.html", {**opcoes, "tipo": tipo, "erro": "Informe a data."})

    observacao = request.POST.get("observacao", "").strip()

    try:
        if tipo in ("aplicacao", "resgate"):
            conta_bancaria_pk = request.POST.get("conta_bancaria")
            conta_bancaria = ContaBancaria.objects.filter(pk=conta_bancaria_pk, operacao=operacao).first() if conta_bancaria_pk else None
            if not conta_bancaria:
                return render(request, "financeiro/private_label/_investimento_transacao_form.html", {**opcoes, "tipo": tipo, "erro": "Selecione a conta bancária."})
            funcao = aplicar if tipo == "aplicacao" else resgatar
            funcao(
                operacao=operacao, conta_investimento=conta_investimento, conta_bancaria=conta_bancaria,
                valor=valor, data=data, observacao=observacao, usuario=request.user,
            )
        else:
            categoria_pk = request.POST.get("categoria")
            categoria = CategoriaFinanceira.objects.filter(pk=categoria_pk, operacao=operacao).first() if categoria_pk else None
            if not categoria:
                return render(request, "financeiro/private_label/_investimento_transacao_form.html", {**opcoes, "tipo": tipo, "erro": "Selecione a categoria."})
            funcao = registrar_rendimento if tipo == "rendimento" else registrar_taxa
            funcao(
                operacao=operacao, conta_investimento=conta_investimento, categoria=categoria,
                valor=valor, data=data, observacao=observacao, usuario=request.user,
            )
    except ValueError as erro:
        return render(request, "financeiro/private_label/_investimento_transacao_form.html", {**opcoes, "tipo": tipo, "erro": str(erro)})

    return _evento("pl:investimentos-mudou")


@perm_required("private_label.lancar")
def pl_htmx_investimento_transacao_estornar(request, pk):
    transacao = get_object_or_404(InvestimentoTransacao, pk=pk)
    if request.method != "POST":
        return _erro_generico(request, "Requisição inválida.")
    try:
        estornar_transacao(transacao, usuario=request.user, motivo="estornada pela tela")
    except ValueError as erro:
        return _erro_generico(request, str(erro))
    return _evento("pl:investimentos-mudou")
