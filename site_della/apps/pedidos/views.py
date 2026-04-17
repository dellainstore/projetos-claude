import json
import logging
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings
from django.db import models, transaction

from .carrinho import Carrinho
from .forms import CheckoutForm

logger = logging.getLogger(__name__)


class _PagamentoRecusado(Exception):
    """Levantada quando o gateway recusa o cartão dentro do bloco atômico."""


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

    # Chave pública PagSeguro para o JS SDK de cartão (falha silenciosa)
    pagseguro_public_key = ''
    try:
        from apps.pagamentos.services.pagseguro import obter_chave_publica
        pagseguro_public_key = obter_chave_publica()
    except Exception:
        pass

    context = {
        'form':                  form,
        'itens':                 itens,
        'subtotal':              subtotal,
        'pagseguro_public_key':  pagseguro_public_key,
    }
    return render(request, 'checkout/index.html', context)


def _processar_checkout(request, form, cart):
    """
    Cria o Pedido e os ItemPedido no banco, processa pagamento e redireciona.

    Para Pix: cria o pedido e redireciona direto para confirmação (QR gerado lá).
    Para Cartão: envolve a criação do pedido + chamada PagSeguro em um bloco
    atômico. Se o cartão for recusado, o pedido é revertido (rollback) e o
    cliente fica no checkout com mensagem de erro — carrinho preservado.
    """
    from .models import Pedido, ItemPedido
    from apps.produtos.models import Produto, Variacao

    from .models import Cupom, CodigoVendedor

    cd              = form.cleaned_data
    subtotal        = cart.get_total()
    frete           = Decimal(str(cd.get('valor_frete') or '0'))
    forma_pagamento = cd['forma_pagamento']
    parcelas        = int(cd.get('parcelas') or 1)

    # Cupom
    cupom_obj     = None
    desconto      = Decimal('0')
    cupom_codigo_str = (cd.get('cupom_codigo') or '').strip().upper()
    if cupom_codigo_str:
        try:
            cupom_obj = Cupom.objects.get(codigo__iexact=cupom_codigo_str, ativo=True)
            cpf_check = cd.get('cpf', '')
            ok, _ = cupom_obj.esta_valido(cpf=cpf_check)
            if ok:
                desconto = cupom_obj.calcular_desconto(subtotal)
            else:
                cupom_obj = None
        except Cupom.DoesNotExist:
            pass

    # Código do vendedor
    vendedor_obj     = None
    vendedor_codigo_str = (cd.get('codigo_vendedor_codigo') or '').strip().upper()
    if vendedor_codigo_str:
        try:
            vendedor_obj = CodigoVendedor.objects.get(codigo__iexact=vendedor_codigo_str, ativo=True)
        except CodigoVendedor.DoesNotExist:
            pass

    total = subtotal - desconto + frete

    # Campo enviado pelo SDK PagSeguro JS (apenas para cartão)
    encrypted_card = request.POST.get('pagseguro_card_encrypted', '').strip()

    if forma_pagamento == 'cartao_credito' and not encrypted_card:
        messages.error(request, 'Dados do cartão não recebidos. Tente novamente.')
        return redirect('pedidos:checkout')

    def _criar_itens(pedido):
        for item in cart:
            try:
                produto_obj = Produto.objects.get(pk=item['produto_id'])
            except Produto.DoesNotExist:
                continue
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

    try:
        with transaction.atomic():
            pedido = Pedido(
                cliente               = request.user if request.user.is_authenticated else None,
                nome_completo         = cd['nome_completo'],
                email                 = cd['email'],
                cpf                   = cd['cpf'],
                telefone              = cd.get('telefone', ''),
                cep_entrega           = cd['cep'],
                logradouro            = cd['logradouro'],
                numero_entrega        = cd['numero_entrega'],
                complemento           = cd.get('complemento', ''),
                bairro                = cd['bairro'],
                cidade                = cd['cidade'],
                estado                = cd['estado'],
                subtotal              = subtotal,
                desconto              = desconto,
                frete                 = frete,
                total                 = total,
                forma_pagamento       = forma_pagamento,
                parcelas              = parcelas,
                transportadora        = cd.get('servico_frete_nome', ''),
                observacao_cliente    = cd.get('observacao', ''),
                gateway               = 'pagseguro' if forma_pagamento == 'cartao_credito' else '',
                cupom                 = cupom_obj,
                cupom_codigo          = cupom_obj.codigo if cupom_obj else '',
                codigo_vendedor       = vendedor_obj,
                codigo_vendedor_str   = vendedor_obj.codigo if vendedor_obj else '',
            )
            pedido.full_clean()
            pedido.save()

            _criar_itens(pedido)

            # ── Processamento de cartão via PagSeguro ─────────────────────────
            if forma_pagamento == 'cartao_credito':
                from apps.pagamentos.services.pagseguro import (
                    criar_ordem_cartao, status_interno, mensagem_recusa,
                )
                resultado    = criar_ordem_cartao(pedido, encrypted_card, parcelas)
                charges      = resultado.get('charges', [])
                charge       = charges[0] if charges else {}
                charge_status = (charge.get('status') or '').upper()
                gateway_order_id = resultado.get('id', '')

                if charge_status == 'DECLINED':
                    raise _PagamentoRecusado(mensagem_recusa(charge))

                # PAID, AUTHORIZED ou IN_ANALYSIS → pedido criado
                novo_status = status_interno(charge_status) or 'aguardando_pagamento'
                pedido.status     = novo_status
                pedido.gateway_id = gateway_order_id
                pedido.save(update_fields=['status', 'gateway_id'])

    except _PagamentoRecusado as e:
        messages.error(request, str(e))
        return redirect('pedidos:checkout')

    except Exception as e:
        logger.error('Erro ao criar pedido: %s', e, exc_info=True)
        messages.error(request, 'Ocorreu um erro ao processar seu pedido. Tente novamente.')
        return redirect('pedidos:checkout')

    # ── Fora do atomic: só executa se o pedido foi commitado ──────────────────
    if cupom_obj:
        from .models import Cupom as _Cupom
        _Cupom.objects.filter(pk=cupom_obj.pk).update(vezes_usado=models.F('vezes_usado') + 1)

    cart.limpar()

    request.session['ultimo_pedido'] = pedido.numero
    pedidos_guest = request.session.get('pedidos_guest', [])
    if pedido.numero not in pedidos_guest:
        pedidos_guest.append(pedido.numero)
        request.session['pedidos_guest'] = pedidos_guest[-20:]

    try:
        from .emails import enviar_confirmacao_pedido
        enviar_confirmacao_pedido(pedido)
    except Exception as exc:
        logger.warning('Não foi possível enviar e-mail de confirmação: %s', exc)

    return redirect('pedidos:confirmacao', numero=pedido.numero)


def confirmacao_pedido(request, numero):
    from .models import Pedido

    pedido = get_object_or_404(Pedido, numero=numero)

    # Segurança: staff, dono logado, ou número na sessão do guest checkout.
    # Qualquer outro caso (inclusive pedido sem cliente acessado por anônimo
    # desconhecido) é bloqueado — fecha IDOR por força bruta do número.
    pedidos_guest = request.session.get('pedidos_guest', [])
    autorizado = (
        (request.user.is_authenticated and request.user.is_staff)
        or (request.user.is_authenticated and pedido.cliente_id == request.user.id)
        or request.session.get('ultimo_pedido') == numero
        or numero in pedidos_guest
    )
    if not autorizado:
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

def validar_cupom(request):
    """AJAX: valida cupom e retorna desconto para o subtotal enviado."""
    from .models import Cupom
    from decimal import Decimal

    codigo   = request.GET.get('codigo', '').strip().upper()
    try:
        subtotal = Decimal(str(request.GET.get('subtotal', '0')))
    except Exception:
        subtotal = Decimal('0')

    cpf = ''
    if request.user.is_authenticated:
        cpf = request.user.cpf

    if not codigo:
        return JsonResponse({'status': 'erro', 'erro': 'Informe o código do cupom.'})

    try:
        cupom = Cupom.objects.get(codigo__iexact=codigo, ativo=True)
    except Cupom.DoesNotExist:
        return JsonResponse({'status': 'erro', 'erro': 'Cupom inválido.'})

    ok, motivo = cupom.esta_valido(cpf=cpf)
    if not ok:
        return JsonResponse({'status': 'erro', 'erro': motivo})

    desconto = cupom.calcular_desconto(subtotal)
    if cupom.tipo == 'percentual':
        descricao = f'{cupom.valor:.0f}% de desconto'
    else:
        v = f'{cupom.valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        descricao = f'R$ {v} de desconto'

    return JsonResponse({
        'status':    'ok',
        'codigo':    cupom.codigo,
        'descricao': descricao,
        'desconto':  str(desconto),
    })


def validar_vendedor(request):
    """AJAX: verifica se o código de vendedor existe e está ativo."""
    from .models import CodigoVendedor

    codigo = request.GET.get('codigo', '').strip().upper()
    if not codigo:
        return JsonResponse({'status': 'erro', 'erro': 'Informe o código do vendedor.'})

    try:
        vendedor = CodigoVendedor.objects.get(codigo__iexact=codigo, ativo=True)
    except CodigoVendedor.DoesNotExist:
        return JsonResponse({'status': 'erro', 'erro': 'Código de vendedor inválido.'})

    return JsonResponse({'status': 'ok', 'codigo': vendedor.codigo, 'nome': vendedor.nome})


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
    from apps.pagamentos.views import _pode_acessar_pedido
    from django.conf import settings as _settings

    pedido = get_object_or_404(Pedido, numero=numero)

    if not _pode_acessar_pedido(request, pedido):
        return redirect('produtos:home')

    # Gera QR Code Pix se o pedido está aguardando pagamento via Pix
    pix_qrcode = None
    pix_payload = None
    if pedido.forma_pagamento == 'pix' and pedido.status == 'aguardando_pagamento':
        try:
            from apps.pagamentos.pix import gerar_payload_pix, gerar_qrcode_base64
            chave_pix = getattr(_settings, 'PIX_CHAVE', '')
            if chave_pix:
                pix_payload = gerar_payload_pix(
                    chave=chave_pix,
                    valor=float(pedido.total),
                    nome_recebedor='DELLA INSTORE',
                    cidade='SAO PAULO',
                    txid=pedido.numero.replace('-', ''),
                    descricao=f'Pedido {pedido.numero}',
                )
                pix_qrcode = gerar_qrcode_base64(pix_payload)
        except Exception as e:
            logger.error('Erro ao gerar QR Code Pix no detalhe: %s', e)

    return render(request, 'pedidos/detalhe_pedido.html', {
        'pedido':      pedido,
        'itens':       pedido.itens.select_related('produto').all(),
        'pix_qrcode':  pix_qrcode,
        'pix_payload': pix_payload,
    })


# ─── Stubs checkout multi-etapa (manter compatibilidade de URLs) ──────────────

def checkout_endereco(request):
    return redirect('pedidos:checkout')


def checkout_entrega(request):
    return redirect('pedidos:checkout')


def checkout_pagamento(request):
    return redirect('pedidos:checkout')
