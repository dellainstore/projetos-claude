import json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .carrinho import Carrinho


def carrinho(request):
    cart = Carrinho(request)
    context = {
        'carrinho': cart,
        'itens': list(cart),
        'total': cart.get_total(),
    }
    return render(request, 'pedidos/carrinho.html', context)


@require_POST
def adicionar_ao_carrinho(request, produto_id):
    from apps.produtos.models import Produto, Variacao

    produto = get_object_or_404(Produto, pk=produto_id, ativo=True)

    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        dados = {}

    variacao_id = dados.get('variacao_id') or request.POST.get('variacao_id')
    quantidade  = int(dados.get('quantidade', 1) or 1)

    variacao = None
    if variacao_id:
        try:
            variacao = Variacao.objects.get(pk=int(variacao_id), produto=produto, ativa=True)
        except (Variacao.DoesNotExist, ValueError):
            pass

    cart = Carrinho(request)
    cart.adicionar(produto, variacao=variacao, quantidade=quantidade)

    # Monta lista de itens para atualizar o drawer via AJAX
    itens_drawer = []
    for item in cart:
        itens_drawer.append({
            'chave':      item['chave'],
            'nome':       item['nome'],
            'variacao':   item.get('variacao_desc', ''),
            'preco':      str(item['preco_decimal']),
            'quantidade': item['quantidade'],
            'subtotal':   str(item['subtotal']),
            'imagem':     item.get('imagem', ''),
        })

    return JsonResponse({
        'status':      'ok',
        'total_itens': len(cart),
        'total_valor': str(cart.get_total()),
        'itens':       itens_drawer,
    })


@require_POST
def remover_do_carrinho(request, item_id):
    cart = Carrinho(request)
    cart.remover(item_id)

    itens_drawer = []
    for item in cart:
        itens_drawer.append({
            'chave':      item['chave'],
            'nome':       item['nome'],
            'variacao':   item.get('variacao_desc', ''),
            'preco':      str(item['preco_decimal']),
            'quantidade': item['quantidade'],
            'subtotal':   str(item['subtotal']),
            'imagem':     item.get('imagem', ''),
        })

    return JsonResponse({
        'status':      'ok',
        'total_itens': len(cart),
        'total_valor': str(cart.get_total()),
        'itens':       itens_drawer,
    })


@require_POST
def atualizar_carrinho(request):
    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        dados = {}

    chave      = dados.get('chave', '')
    quantidade = int(dados.get('quantidade', 1) or 1)

    cart = Carrinho(request)
    cart.atualizar(chave, quantidade)

    itens_drawer = []
    for item in cart:
        itens_drawer.append({
            'chave':      item['chave'],
            'nome':       item['nome'],
            'variacao':   item.get('variacao_desc', ''),
            'preco':      str(item['preco_decimal']),
            'quantidade': item['quantidade'],
            'subtotal':   str(item['subtotal']),
            'imagem':     item.get('imagem', ''),
        })

    return JsonResponse({
        'status':      'ok',
        'total_itens': len(cart),
        'total_valor': str(cart.get_total()),
        'itens':       itens_drawer,
    })


def checkout(request):
    return render(request, 'checkout/index.html')


def checkout_endereco(request):
    return render(request, 'checkout/endereco.html')


def checkout_entrega(request):
    return render(request, 'checkout/entrega.html')


def checkout_pagamento(request):
    return render(request, 'checkout/pagamento.html')


def confirmacao_pedido(request, numero):
    return render(request, 'checkout/confirmacao.html')


def meus_pedidos(request):
    return render(request, 'pedidos/meus_pedidos.html')


def detalhe_pedido(request, numero):
    return render(request, 'pedidos/detalhe_pedido.html')


def consultar_cep(request, cep):
    import re
    import requests as req

    cep_limpo = re.sub(r'\D', '', cep)
    if len(cep_limpo) != 8:
        return JsonResponse({'status': 'erro', 'erro': 'CEP inválido.'})

    try:
        r = req.get(f'https://viacep.com.br/ws/{cep_limpo}/json/', timeout=5)
        dados = r.json()
        if dados.get('erro'):
            return JsonResponse({'status': 'erro', 'erro': 'CEP não encontrado.'})
        return JsonResponse({
            'status':      'ok',
            'logradouro':  dados.get('logradouro', ''),
            'bairro':      dados.get('bairro', ''),
            'cidade':      dados.get('localidade', ''),
            'estado':      dados.get('uf', ''),
        })
    except Exception:
        return JsonResponse({'status': 'erro', 'erro': 'Serviço indisponível.'})


def calcular_frete(request):
    return JsonResponse({'status': 'ok', 'opcoes': []})
