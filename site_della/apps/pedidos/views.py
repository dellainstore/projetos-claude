import json
import logging
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings

from .carrinho import Carrinho
from .forms import CheckoutForm

logger = logging.getLogger(__name__)


# ─── Carrinho ─────────────────────────────────────────────────────────────────

def carrinho(request):
    cart = Carrinho(request)
    context = {
        'carrinho': cart,
        'itens':    list(cart),
        'total':    cart.get_total(),
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

    itens_drawer = _itens_para_drawer(cart)
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
    return JsonResponse({
        'status':      'ok',
        'total_itens': len(cart),
        'total_valor': str(cart.get_total()),
        'itens':       _itens_para_drawer(cart),
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
    return JsonResponse({
        'status':      'ok',
        'total_itens': len(cart),
        'total_valor': str(cart.get_total()),
        'itens':       _itens_para_drawer(cart),
    })


def _itens_para_drawer(cart):
    return [
        {
            'chave':      item['chave'],
            'nome':       item['nome'],
            'variacao':   item.get('variacao_desc', ''),
            'preco':      str(item['preco_decimal']),
            'quantidade': item['quantidade'],
            'subtotal':   str(item['subtotal']),
            'imagem':     item.get('imagem', ''),
        }
        for item in cart
    ]


# ─── Checkout ─────────────────────────────────────────────────────────────────

def checkout(request):
    cart = Carrinho(request)

    # Carrinho vazio → volta para a loja
    if len(cart) == 0:
        messages.warning(request, 'Seu carrinho está vazio.')
        return redirect('produtos:loja')

    # Pré-preenche com dados do usuário logado
    initial = {}
    if request.user.is_authenticated:
        u = request.user
        initial['nome_completo'] = u.get_full_name()
        initial['email']         = u.email
        initial['cpf']           = u.cpf
        initial['telefone']      = u.telefone

        # Endereço principal salvo
        try:
            end = u.enderecos.filter(principal=True).first() or u.enderecos.first()
            if end:
                initial.update({
                    'cep':           end.cep,
                    'logradouro':    end.logradouro,
                    'numero_entrega': end.numero,
                    'complemento':   end.complemento,
                    'bairro':        end.bairro,
                    'cidade':        end.cidade,
                    'estado':        end.estado,
                })
        except Exception:
            pass

    if request.method == 'POST':
        form = CheckoutForm(request.POST, initial=initial)
        if form.is_valid():
            return _processar_checkout(request, form, cart)
        # Form inválido → renderiza de volta com erros
    else:
        form = CheckoutForm(initial=initial)

    itens = list(cart)
    subtotal = cart.get_total()

    context = {
        'form':     form,
        'itens':    itens,
        'subtotal': subtotal,
    }
    return render(request, 'checkout/index.html', context)


def _processar_checkout(request, form, cart):
    """Cria o Pedido e os ItemPedido no banco. Redireciona para confirmação."""
    from .models import Pedido, ItemPedido
    from apps.produtos.models import Produto

    cd = form.cleaned_data
    subtotal = cart.get_total()
    frete    = Decimal(str(cd.get('valor_frete') or '0'))
    total    = subtotal + frete

    try:
        pedido = Pedido(
            cliente        = request.user if request.user.is_authenticated else None,
            nome_completo  = cd['nome_completo'],
            email          = cd['email'],
            cpf            = cd['cpf'],
            telefone       = cd.get('telefone', ''),
            cep_entrega    = cd['cep'],
            logradouro     = cd['logradouro'],
            numero_entrega = cd['numero_entrega'],
            complemento    = cd.get('complemento', ''),
            bairro         = cd['bairro'],
            cidade         = cd['cidade'],
            estado         = cd['estado'],
            subtotal       = subtotal,
            frete          = frete,
            total          = total,
            forma_pagamento= cd['forma_pagamento'],
            parcelas       = int(cd.get('parcelas') or 1),
            transportadora = cd.get('servico_frete_nome', ''),
            observacao_cliente = cd.get('observacao', ''),
        )
        pedido.full_clean()
        pedido.save()

        # Cria itens copiando dados do produto (imutável após compra)
        for item in cart:
            try:
                produto_obj = Produto.objects.get(pk=item['produto_id'])
            except Produto.DoesNotExist:
                continue

            from apps.produtos.models import Variacao
            variacao_obj = None
            if item.get('variacao_id'):
                try:
                    variacao_obj = Variacao.objects.get(pk=item['variacao_id'])
                except Variacao.DoesNotExist:
                    pass

            ItemPedido.objects.create(
                pedido         = pedido,
                produto        = produto_obj,
                variacao       = variacao_obj,
                nome_produto   = item['nome'],
                sku            = produto_obj.sku,
                variacao_desc  = item.get('variacao_desc', ''),
                preco_unitario = Decimal(item['preco']),
                quantidade     = item['quantidade'],
            )

        # Limpa o carrinho
        cart.limpar()

        # Salva número do pedido na sessão (para exibir confirmação)
        request.session['ultimo_pedido'] = pedido.numero

        return redirect('pedidos:confirmacao', numero=pedido.numero)

    except Exception as e:
        logger.error('Erro ao criar pedido: %s', e, exc_info=True)
        messages.error(request, 'Ocorreu um erro ao processar seu pedido. Tente novamente.')
        return redirect('pedidos:checkout')


def confirmacao_pedido(request, numero):
    from .models import Pedido

    pedido = get_object_or_404(Pedido, numero=numero)

    # Segurança: apenas o dono do pedido ou admin pode ver
    if pedido.cliente and request.user.is_authenticated:
        if pedido.cliente != request.user and not request.user.is_staff:
            return redirect('pedidos:checkout')
    elif pedido.cliente and not request.user.is_authenticated:
        # Permite acesso se veio do fluxo desta sessão
        if request.session.get('ultimo_pedido') != numero:
            return redirect('produtos:home')

    # Gera QR Code Pix se for forma de pagamento Pix
    pix_qrcode = None
    pix_payload = None
    if pedido.forma_pagamento == 'pix':
        try:
            from apps.pagamentos.pix import gerar_payload_pix, gerar_qrcode_base64
            chave_pix = getattr(settings, 'PIX_CHAVE', '')
            if chave_pix:
                pix_payload = gerar_payload_pix(
                    chave          = chave_pix,
                    valor          = float(pedido.total),
                    nome_recebedor = 'DELLA INSTORE',
                    cidade         = 'SAO PAULO',
                    txid           = pedido.numero.replace('-', ''),
                    descricao      = f'Pedido {pedido.numero}',
                )
                pix_qrcode = gerar_qrcode_base64(pix_payload)
        except Exception as e:
            logger.error('Erro ao gerar QR Code Pix: %s', e)

    context = {
        'pedido':      pedido,
        'itens':       pedido.itens.select_related('produto').all(),
        'pix_qrcode':  pix_qrcode,
        'pix_payload': pix_payload,
    }
    return render(request, 'checkout/confirmacao.html', context)


# ─── Frete ────────────────────────────────────────────────────────────────────

def calcular_frete(request):
    cep = request.GET.get('cep', '').strip()
    if not cep or len(''.join(filter(str.isdigit, cep))) != 8:
        return JsonResponse({'status': 'erro', 'erro': 'CEP inválido.'})

    cart  = Carrinho(request)
    itens = [
        {'quantidade': item['quantidade'], 'preco': item['preco']}
        for item in cart
    ]
    valor_declarado = float(cart.get_total())

    from apps.pagamentos.services.melhorenvio import calcular
    opcoes = calcular(cep, itens, valor_declarado)

    return JsonResponse({
        'status': 'ok',
        'opcoes': [
            {
                'id':        o['id'],
                'nome':      o['nome'],
                'empresa':   o['empresa'],
                'preco':     str(o['preco']),
                'prazo':     o['prazo'],
                'descricao': o['descricao'],
            }
            for o in opcoes
        ],
    })


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
            'status':     'ok',
            'logradouro': dados.get('logradouro', ''),
            'bairro':     dados.get('bairro', ''),
            'cidade':     dados.get('localidade', ''),
            'estado':     dados.get('uf', ''),
        })
    except Exception:
        return JsonResponse({'status': 'erro', 'erro': 'Serviço de CEP indisponível.'})


# ─── Pedidos do cliente ────────────────────────────────────────────────────────

def meus_pedidos(request):
    from .models import Pedido
    pedidos = []
    if request.user.is_authenticated:
        pedidos = Pedido.objects.filter(cliente=request.user).order_by('-criado_em')
    return render(request, 'pedidos/meus_pedidos.html', {'pedidos': pedidos})


def detalhe_pedido(request, numero):
    from .models import Pedido
    pedido = get_object_or_404(Pedido, numero=numero)
    if pedido.cliente and request.user.is_authenticated:
        if pedido.cliente != request.user and not request.user.is_staff:
            return redirect('usuarios:minha_conta')
    return render(request, 'pedidos/detalhe_pedido.html', {
        'pedido': pedido,
        'itens':  pedido.itens.select_related('produto').all(),
    })


# ─── Stubs checkout multi-etapa (manter compatibilidade de URLs) ──────────────

def checkout_endereco(request):
    return redirect('pedidos:checkout')


def checkout_entrega(request):
    return redirect('pedidos:checkout')


def checkout_pagamento(request):
    return redirect('pedidos:checkout')
