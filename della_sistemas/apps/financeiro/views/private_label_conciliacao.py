"""Conciliação bancária (Fase 3) — upload de extrato OFX/CSV + revisão das
sugestões de conciliação. Ver `services/private_label/extrato.py`.

Upload é um POST comum (não HTMX) — arquivo multipart + redirect simples é
mais robusto que tentar encaixar no padrão de modal HTMX do resto do
módulo (evita lidar com upload de arquivo grande dentro de um swap)."""
from datetime import timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.decorators import perm_required
from apps.financeiro.models import (
    Conciliacao,
    ContaBancaria,
    ImportacaoExtrato,
    ItemExtrato,
    MovimentoConta,
)
from apps.financeiro.services.private_label.extrato import (
    ExtratoInvalido,
    conciliar_manualmente,
    confirmar_conciliacao,
    desfazer_conciliacao,
    ignorar_item,
    importar_extrato,
    rejeitar_conciliacao,
)
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao


def _evento(nome_evento: str) -> HttpResponse:
    resposta = HttpResponse("")
    resposta["HX-Trigger"] = nome_evento
    return resposta


@perm_required("private_label.conciliar")
def pl_conciliacao(request):
    operacao = obter_operacao_padrao()
    if request.method == "POST":
        conta_pk = request.POST.get("conta")
        arquivo = request.FILES.get("arquivo")
        conta = ContaBancaria.objects.filter(pk=conta_pk, operacao=operacao).first()
        if not conta or not arquivo:
            messages.error(request, "Selecione a conta e o arquivo do extrato.")
        else:
            try:
                importacao = importar_extrato(operacao=operacao, conta=conta, arquivo_upload=arquivo, usuario=request.user)
                messages.success(request, f"{importacao.total_itens} transações importadas de '{importacao.nome_original}'.")
                return redirect("financeiro:pl_conciliacao_detalhe", pk=importacao.pk)
            except ExtratoInvalido as erro:
                messages.error(request, str(erro))
        return redirect("financeiro:pl_conciliacao")

    importacoes = ImportacaoExtrato.objects.filter(operacao=operacao).select_related("conta")[:20]
    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    return render(request, "financeiro/private_label/conciliacao.html", {
        "importacoes": importacoes, "contas": contas,
    })


@perm_required("private_label.conciliar")
def pl_conciliacao_detalhe(request, pk):
    importacao = get_object_or_404(ImportacaoExtrato, pk=pk, operacao=obter_operacao_padrao())
    return render(request, "financeiro/private_label/conciliacao_detalhe.html", _contexto_detalhe(importacao))


def _contexto_detalhe(importacao):
    itens = (
        importacao.itens.prefetch_related("conciliacoes")
        .order_by("status", "-data")
    )
    linhas = []
    for item in itens:
        sugestao = next(
            (c for c in item.conciliacoes.all() if c.status in ("sugerido", "confirmado") and not c.desfeita_em),
            None,
        )
        linhas.append({"item": item, "conciliacao": sugestao})
    return {"importacao": importacao, "linhas": linhas}


@perm_required("private_label.conciliar")
def pl_htmx_conciliacao_detalhe_conteudo(request, pk):
    importacao = get_object_or_404(ImportacaoExtrato, pk=pk, operacao=obter_operacao_padrao())
    return render(request, "financeiro/private_label/_conciliacao_itens.html", _contexto_detalhe(importacao))


@perm_required("private_label.conciliar")
def pl_htmx_conciliacao_confirmar(request, pk):
    conciliacao = get_object_or_404(Conciliacao, pk=pk)
    if request.method == "POST":
        confirmar_conciliacao(conciliacao, usuario=request.user)
    return _evento("pl:conciliacao-mudou")


@perm_required("private_label.conciliar")
def pl_htmx_conciliacao_rejeitar(request, pk):
    conciliacao = get_object_or_404(Conciliacao, pk=pk)
    if request.method == "POST":
        rejeitar_conciliacao(conciliacao, usuario=request.user)
    return _evento("pl:conciliacao-mudou")


@perm_required("private_label.conciliar")
def pl_htmx_conciliacao_desfazer(request, pk):
    conciliacao = get_object_or_404(Conciliacao, pk=pk)
    if request.method == "POST":
        desfazer_conciliacao(conciliacao, usuario=request.user)
    return _evento("pl:conciliacao-mudou")


@perm_required("private_label.conciliar")
def pl_htmx_item_ignorar(request, pk):
    item = get_object_or_404(ItemExtrato, pk=pk)
    if request.method == "POST":
        ignorar_item(item)
    return _evento("pl:conciliacao-mudou")


def _candidatos_para_item(item):
    return (
        MovimentoConta.objects.filter(
            conta=item.importacao.conta, data__gte=item.data - timedelta(days=10),
            data__lte=item.data + timedelta(days=10),
        )
        .exclude(conciliacoes__status__in=["sugerido", "confirmado"], conciliacoes__desfeita_em__isnull=True)
        .order_by("-data")
    )


@perm_required("private_label.conciliar")
def pl_htmx_item_vincular_form(request, pk):
    item = get_object_or_404(ItemExtrato, pk=pk)
    return render(request, "financeiro/private_label/_item_vincular_form.html", {
        "item": item, "candidatos": _candidatos_para_item(item),
    })


@perm_required("private_label.conciliar")
def pl_htmx_item_vincular_salvar(request, pk):
    item = get_object_or_404(ItemExtrato, pk=pk)
    movimento_pk = request.POST.get("movimento")
    movimento = MovimentoConta.objects.filter(pk=movimento_pk).first() if movimento_pk else None
    if not movimento:
        return render(request, "financeiro/private_label/_item_vincular_form.html", {
            "item": item, "candidatos": _candidatos_para_item(item), "erro": "Selecione um movimento.",
        })
    try:
        conciliar_manualmente(item, movimento, usuario=request.user)
    except ValueError as erro:
        return render(request, "financeiro/private_label/_item_vincular_form.html", {
            "item": item, "candidatos": _candidatos_para_item(item), "erro": str(erro),
        })
    return _evento("pl:conciliacao-mudou")
