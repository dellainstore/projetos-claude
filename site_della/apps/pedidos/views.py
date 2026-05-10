import json
import logging
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import models, transaction

from .carrinho import Carrinho, calcular_qtd_disponivel
from .forms import CheckoutForm
from .services.checkout import CalculadorPedido, criar_itens_pedido, EstoqueInsuficiente as _EstoqueInsuficiente
from apps.core_utils.meta import enviar_evento_meta, enviar_evento_purchase, gerar_evento_id

logger = logging.getLogger(__name__)


def _salvar_carrinho_abandonado(request, cart):
    """Persiste (ou atualiza) o snapshot do carrinho no banco para o usuário logado."""
    if not request.user.is_authenticated:
        return
    if len(cart) == 0:
        return
    try:
        from .models import CarrinhoAbandonado
        itens = [
            {
                'nome':         item['nome'],
                'variacao_desc': item.get('variacao_desc', ''),
                'preco':        str(item['preco_decimal']),
                'quantidade':   item['quantidade'],
                'subtotal':     str(item['subtotal']),
                'imagem':       item.get('imagem', ''),
            }
            for item in cart
        ]
        CarrinhoAbandonado.objects.update_or_create(
            cliente=request.user,
            defaults={
                'email':       request.user.email,
                'nome':        request.user.get_full_name(),
                'itens_json':  itens,
                'total':       cart.get_total(),
                'recuperado':  False,
            },
        )
    except Exception as exc:
        logger.debug('Não foi possível salvar carrinho abandonado: %s', exc)


def _limpar_carrinho_abandonado(request):
    """Marca o carrinho como recuperado após checkout bem-sucedido."""
    if not request.user.is_authenticated:
        return
    try:
        from .models import CarrinhoAbandonado
        CarrinhoAbandonado.objects.filter(cliente=request.user).update(recuperado=True)
    except Exception as exc:
        logger.debug('Não foi possível marcar carrinho como recuperado: %s', exc)


class _PagamentoRecusado(Exception):
    """Levantada quando o gateway recusa o cartão dentro do bloco atômico."""


def _gerar_dados_pix(pedido):
    """
    Gera dados de Pix para um pedido.

    Prioriza Pix dinâmico via gateway (com webhook e confirmação automática).
    Se a API não estiver disponível/liberada, faz fallback para Pix estático local.
    """
    pix_qrcode = None
    pix_payload = None
    pix_via = None

    try:
        from apps.pagamentos.services.pagseguro import criar_ordem_pix
        from apps.pagamentos.pix import gerar_qrcode_base64

        resposta = criar_ordem_pix(pedido)
        qr_codes = resposta.get('qr_codes', [])
        order_id = resposta.get('id', '')

        if qr_codes and order_id:
            pix_payload = qr_codes[0].get('text', '')
            if pix_payload:
                pix_qrcode = gerar_qrcode_base64(pix_payload)
                pix_via = 'pagseguro'
                if pedido.gateway != 'pagseguro' or pedido.gateway_id != order_id:
                    pedido.gateway = 'pagseguro'
                    pedido.gateway_id = order_id
                    pedido.save(update_fields=['gateway', 'gateway_id'])
                return pix_qrcode, pix_payload, pix_via
    except Exception as exc:
        logger.warning('PIX do gateway indisponível para pedido %s: %s', pedido.numero, exc)

    try:
        from apps.pagamentos.pix import gerar_payload_pix, gerar_qrcode_base64

        chave_pix = getattr(settings, 'PIX_CHAVE', '')
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
            pix_via = 'estatico'
    except Exception as exc:
        logger.error('Erro ao gerar QR Code Pix estático para pedido %s: %s', pedido.numero, exc)

    return pix_qrcode, pix_payload, pix_via


# ─── Carrinho ─────────────────────────────────────────────────────────────────

def carrinho(request):
    cart = Carrinho(request)
    context = {
        'carrinho': cart,
        'itens':    list(cart),
        'total':    cart.get_total(),
    }
    return render(request, 'pedidos/carrinho.html', context)


def carrinho_status(request):
    """Retorna o estado atual do carrinho em JSON — usado pelo drawer para sincronizar badge."""
    cart = Carrinho(request)
    return JsonResponse({
        'total_itens': len(cart),
        'itens': _itens_para_drawer(cart),
        'total_valor': str(cart.get_total()),
    })


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

    if variacao:
        chave = cart._chave(produto.id, variacao.id)
        qtd_no_carrinho = cart.carrinho.get(chave, {}).get('quantidade', 0)
        quantidade = calcular_qtd_disponivel(variacao, quantidade, qtd_no_carrinho)
        if quantidade <= 0:
            return JsonResponse({'status': 'ok', 'total_itens': len(cart),
                                 'total_valor': str(cart.get_total()),
                                 'itens': _itens_para_drawer(cart)})

    cart.adicionar(produto, variacao=variacao, quantidade=quantidade)
    _salvar_carrinho_abandonado(request, cart)

    meta_event_id = (dados.get('meta_event_id') or '').strip()
    if meta_event_id:
        preco_item = variacao.preco_atual if variacao else produto.preco_atual
        try:
            enviar_evento_meta(
                request,
                event_name='AddToCart',
                event_id=meta_event_id,
                event_source_url=request.build_absolute_uri(produto.get_absolute_url()),
                custom_data={
                    'content_ids': [str(produto.id)],
                    'content_type': 'product',
                    'content_name': produto.nome,
                    'currency': 'BRL',
                    'value': float(preco_item) * quantidade,
                    'contents': [
                        {
                            'id': str(produto.id),
                            'quantity': quantidade,
                            'item_price': float(preco_item),
                        }
                    ],
                },
            )
        except Exception as exc:
            logger.warning('Meta CAPI: não foi possível enviar AddToCart do produto %s: %s', produto.id, exc)

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

    chave = dados.get('chave', '')
    try:
        quantidade = int(dados.get('quantidade', 1))
    except (TypeError, ValueError):
        quantidade = 1

    cart = Carrinho(request)
    if quantidade <= 0:
        cart.remover(chave)
    else:
        cart_item = cart.carrinho.get(chave)
        if cart_item and cart_item.get('variacao_id'):
            from apps.produtos.models import Variacao
            try:
                variacao = Variacao.objects.get(pk=cart_item['variacao_id'])
                quantidade = calcular_qtd_disponivel(variacao, quantidade)
            except Variacao.DoesNotExist:
                pass
        if quantidade <= 0:
            cart.remover(chave)
        else:
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

@login_required(login_url='/conta/entrar/')
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
        initial['telefone']      = u.get_telefone_formatado()

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
    pagseguro_public_key = ''
    cartao_habilitado = False

    try:
        from apps.pagamentos.services.pagseguro import obter_chave_publica
        pagseguro_public_key = obter_chave_publica()
    except Exception:
        pagseguro_public_key = ''

    cartao_habilitado = bool(pagseguro_public_key)
    meta_initiatecheckout_event_id = gerar_evento_id('initiatecheckout')

    context = {
        'form':                  form,
        'itens':                 itens,
        'subtotal':              subtotal,
        'total_itens':           sum(item['quantidade'] for item in itens),
        'pagseguro_public_key':  pagseguro_public_key,
        'cartao_habilitado':     cartao_habilitado,
        'pagseguro_sandbox':     bool(settings.PAGSEGURO_SANDBOX),
        'meta_initiatecheckout_event_id': meta_initiatecheckout_event_id,
    }
    try:
        enviar_evento_meta(
            request,
            event_name='InitiateCheckout',
            event_id=meta_initiatecheckout_event_id,
            event_source_url=request.build_absolute_uri('/carrinho/checkout/'),
            custom_data={
                'value': float(subtotal),
                'currency': 'BRL',
                'num_items': sum(item['quantidade'] for item in itens),
            },
        )
    except Exception:
        pass
    return render(request, 'checkout/index.html', context)


def _processar_checkout(request, form, cart):
    """
    Cria o Pedido e os ItemPedido no banco, processa pagamento e redireciona.

    Para Pix: cria o pedido e redireciona direto para confirmação (QR gerado lá).
    Para Cartão: envolve a criação do pedido + chamada PagSeguro em um bloco
    atômico. Se o cartão for recusado, o pedido é revertido (rollback) e o
    cliente fica no checkout com mensagem de erro — carrinho preservado.
    """
    from .models import Pedido

    cd              = form.cleaned_data
    subtotal        = cart.get_total()
    frete           = Decimal(str(cd.get('valor_frete') or '0'))
    forma_pagamento = cd['forma_pagamento']
    parcelas        = int(cd.get('parcelas') or 1)

    calculo = CalculadorPedido().calcular(
        subtotal=subtotal,
        cupom_codigo=cd.get('cupom_codigo', ''),
        cpf=cd.get('cpf', ''),
        valor_frete=frete,
        vendedor_codigo=cd.get('codigo_vendedor_codigo', ''),
    )
    cupom_obj   = calculo.cupom_obj
    vendedor_obj = calculo.vendedor_obj
    desconto    = calculo.desconto
    total       = calculo.total

    # Campo enviado pelo SDK PagSeguro JS (apenas para cartão)
    encrypted_card = request.POST.get('pagseguro_card_encrypted', '').strip()

    if forma_pagamento == 'cartao_credito' and not encrypted_card:
        messages.error(request, 'Dados do cartão não recebidos. Tente novamente.')
        return redirect('pedidos:checkout')

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
                frete_servico_id      = (cd.get('opcao_frete') or '').strip(),
                frete_prazo_dias      = cd.get('prazo_frete') or None,
                observacao_cliente    = cd.get('observacao', ''),
                gateway               = 'pagseguro' if forma_pagamento == 'cartao_credito' else '',
                cupom                 = cupom_obj,
                cupom_codigo          = cupom_obj.codigo if cupom_obj else '',
                codigo_vendedor       = vendedor_obj,
                codigo_vendedor_str   = vendedor_obj.codigo if vendedor_obj else '',
            )
            pedido.full_clean()
            pedido.save()

            criar_itens_pedido(pedido, cart)

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

    except _EstoqueInsuficiente as e:
        messages.error(request, str(e))
        return redirect('pedidos:carrinho')

    except Exception as e:
        import requests as _req
        if isinstance(e, _req.HTTPError) and e.response is not None:
            logger.error(
                'Erro PagSeguro ao criar pedido: HTTP %s — %s',
                e.response.status_code, e.response.text[:800], exc_info=False,
            )
            # Tenta extrair mensagem legível da resposta PagSeguro
            try:
                erros = e.response.json().get('error_messages', [])
                descricao = '; '.join(
                    f"{err.get('code','')}: {err.get('description','')}" for err in erros
                ) if erros else e.response.text[:200]
            except Exception:
                descricao = e.response.text[:200]
            messages.error(request, f'Erro no gateway de pagamento: {descricao}')
        else:
            logger.error('Erro ao criar pedido: %s', e, exc_info=True)
            messages.error(request, 'Ocorreu um erro ao processar seu pedido. Tente novamente.')
        return redirect('pedidos:checkout')

    # ── Fora do atomic: só executa se o pedido foi commitado ──────────────────
    if cupom_obj:
        from .models import Cupom as _Cupom
        _Cupom.objects.filter(pk=cupom_obj.pk).update(vezes_usado=models.F('vezes_usado') + 1)

    cart.limpar()
    _limpar_carrinho_abandonado(request)

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

    # Envio ao Bling — fora do atomic para não afetar o checkout se o Bling falhar
    try:
        from apps.bling.services import enviar_pedido_bling
        enviar_pedido_bling(pedido)
    except Exception as exc:
        logger.warning('Bling: não foi possível enviar pedido %s: %s', pedido.numero, exc)

    try:
        enviar_evento_purchase(pedido, request)
    except Exception as exc:
        logger.warning('Meta CAPI: não foi possível enviar Purchase do pedido %s: %s', pedido.numero, exc)

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

    # Gera QR Code Pix apenas via gateway dinâmico (sem fallback estático).
    # Pula a geração se o pedido já foi pago/cancelado — evita criar nova ordem
    # no PagBank ao recarregar a página de confirmação.
    pix_qrcode = None
    pix_payload = None
    pix_via = None
    if pedido.forma_pagamento == 'pix' and pedido.status not in ('pagamento_confirmado', 'cancelado'):
        pix_qrcode, pix_payload, pix_via = _gerar_dados_pix(pedido)

    context = {
        'pedido':      pedido,
        'itens':       pedido.itens.select_related('produto').all(),
        'pix_qrcode':  pix_qrcode,
        'pix_payload': pix_payload,
        'pix_via':     pix_via,
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

    # Quando a página de produto passa preco+quantidade, usa esses valores diretamente
    # (ignora o carrinho) para que o frete calculado no produto seja idêntico ao do checkout.
    preco_param = request.GET.get('preco', '').strip()
    prazo_adicional = 0
    if preco_param:
        try:
            preco_unit = float((preco_param or '0').replace(',', '.'))
            qtd        = max(1, int(request.GET.get('quantidade', '1') or 1))
            peso       = max(1, int(request.GET.get('peso', '500') or 500))
            prazo_adicional = max(0, int(request.GET.get('prazo_adicional', '0') or 0))
        except (ValueError, TypeError):
            preco_unit, qtd, peso, prazo_adicional = 0.0, 1, 500, 0
        itens = [{'quantidade': qtd, 'preco': str(preco_unit or 1), 'peso': peso}]
    else:
        cart  = Carrinho(request)
        itens = [
            {'quantidade': item['quantidade'], 'preco': item['preco'], 'peso': item.get('peso', 500)}
            for item in cart
        ]
        from apps.produtos.models import Variacao
        variacao_ids = [item.get('variacao_id') for item in cart if item.get('variacao_id')]
        if variacao_ids:
            from django.db.models import Max
            prazo_adicional = (
                Variacao.objects
                .filter(pk__in=variacao_ids)
                .aggregate(maior=Max('prazo_confeccao_dias'))
                .get('maior')
                or 0
            )
        if not itens:
            itens = [{'quantidade': 1, 'preco': '1', 'peso': 500}]

    from apps.pagamentos.services.melhorenvio import calcular
    opcoes = calcular(cep, itens)

    return JsonResponse({
        'status': 'ok',
        'opcoes': [
            {
                'id':        o['id'],
                'nome':      o['nome'],
                'empresa':   o['empresa'],
                'preco':     str(o['preco']),
                'prazo':     (o['prazo'] or 0) + prazo_adicional,
                'descricao': (
                    f'Entrega em até {(o["prazo"] or 0) + prazo_adicional} dias úteis'
                    + (f' ({prazo_adicional} de confecção + {(o["prazo"] or 0)} de frete)' if prazo_adicional else '')
                ),
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

    pedido = get_object_or_404(Pedido, numero=numero)

    if not _pode_acessar_pedido(request, pedido):
        return redirect('produtos:home')

    # Gera QR Code Pix se o pedido está aguardando pagamento via Pix
    pix_qrcode = None
    pix_payload = None
    pix_via = None
    if pedido.forma_pagamento == 'pix' and pedido.status == 'aguardando_pagamento':
        pix_qrcode, pix_payload, pix_via = _gerar_dados_pix(pedido)

    return render(request, 'pedidos/detalhe_pedido.html', {
        'pedido':      pedido,
        'itens':       pedido.itens.select_related('produto').all(),
        'pix_qrcode':  pix_qrcode,
        'pix_payload': pix_payload,
        'pix_via':     pix_via,
    })


# ─── Stubs checkout multi-etapa (manter compatibilidade de URLs) ──────────────

def checkout_endereco(request):
    return redirect('pedidos:checkout')


def checkout_entrega(request):
    return redirect('pedidos:checkout')


def checkout_pagamento(request):
    return redirect('pedidos:checkout')


# ─── Webhook Melhor Envio ─────────────────────────────────────────────────────

import hashlib
import hmac
import base64

from django.views.decorators.csrf import csrf_exempt


def _validar_assinatura_me(raw_body: bytes, assinatura: str) -> bool:
    secret = getattr(settings, 'MELHOR_ENVIO_WEBHOOK_SECRET', '')
    if not secret:
        logger.warning('MELHOR_ENVIO_WEBHOOK_SECRET não configurado — rejeitando webhook ME')
        return False
    chave = secret.encode('utf-8')
    esperado = base64.b64encode(
        hmac.new(chave, raw_body, hashlib.sha256).digest()
    ).decode('utf-8')
    return hmac.compare_digest(esperado, assinatura)


@csrf_exempt
@require_POST
def webhook_melhorenvio(request):
    """Recebe e processa eventos de rastreio do Melhor Envio."""
    from .models import Pedido, HistoricoPedido, RastreioEvento
    from .emails import enviar_notificacao_envio, enviar_confirmacao_entrega

    assinatura = request.headers.get('x-me-signature', '')
    if not _validar_assinatura_me(request.body, assinatura):
        # ME envia um POST sem assinatura ao registrar/validar o webhook.
        # Retornamos 200 mas não processamos o evento — seguro porque sem
        # assinatura válida nenhuma ação real é executada.
        logger.warning('Webhook ME: assinatura inválida ou ping de validação — ignorando')
        return JsonResponse({'status': 'recebido'})

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'erro': 'payload inválido'}, status=400)

    evento      = payload.get('event', '')
    data        = payload.get('data', {})
    me_order_id = data.get('id', '')
    tracking    = (data.get('tracking') or '').strip()

    logger.info('Webhook ME recebido: %s | ME ID: %s | tracking: %s', evento, me_order_id, tracking or '—')

    # Persiste o evento para auditoria antes de qualquer processamento
    rastreio_evt = RastreioEvento(
        me_order_id=me_order_id,
        evento=evento,
        tracking=tracking,
        dados_raw=payload,
    )

    # Tenta encontrar o pedido: primeiro pelo me_order_id já salvo, depois pelo tracking
    pedido = None
    if me_order_id:
        pedido = Pedido.objects.filter(me_order_id=me_order_id).first()
    if pedido is None and tracking:
        pedido = Pedido.objects.filter(codigo_rastreio=tracking).first()

    rastreio_evt.pedido = pedido
    rastreio_evt.save()

    if pedido is None:
        logger.warning('Webhook ME: pedido não encontrado para ME ID=%s tracking=%s', me_order_id, tracking or '—')
        return JsonResponse({'status': 'pedido_nao_encontrado'})

    # Armazena me_order_id para correlacionar eventos futuros
    if me_order_id and not pedido.me_order_id:
        pedido.me_order_id = me_order_id
        pedido.save(update_fields=['me_order_id', 'atualizado_em'])

    with transaction.atomic():
        if evento == 'order.posted':
            _processar_postagem(pedido, data)

        elif evento == 'order.delivered':
            _processar_entrega(pedido, data)

        elif evento == 'order.undelivered':
            logger.warning('Webhook ME: tentativa de entrega falhou | pedido %s', pedido.numero)
            HistoricoPedido.objects.create(
                pedido=pedido,
                status_anterior=pedido.status,
                status_novo=pedido.status,
                observacao='Tentativa de entrega falhou (Melhor Envio webhook order.undelivered).',
            )

    return JsonResponse({'status': 'ok'})


def _processar_postagem(pedido, data):
    """order.posted — pacote postado nos Correios → marca enviado + e-mail."""
    from .models import HistoricoPedido
    from .emails import enviar_notificacao_envio

    status_aptos = ('pagamento_confirmado', 'em_separacao')
    if pedido.status not in status_aptos:
        logger.info('Webhook ME order.posted: pedido %s já em status=%s, ignorando mudança',
                    pedido.numero, pedido.status)
        return

    status_anterior = pedido.status
    pedido.status = 'enviado'
    campos = ['status', 'atualizado_em']

    # Atualiza código de rastreio se ainda não tiver (pode ter vindo antes via Bling)
    tracking = (data.get('tracking') or '').strip()
    if tracking and not pedido.codigo_rastreio:
        pedido.codigo_rastreio = tracking
        campos.append('codigo_rastreio')

    pedido.save(update_fields=campos)

    HistoricoPedido.objects.create(
        pedido=pedido,
        status_anterior=status_anterior,
        status_novo='enviado',
        observacao='Pacote postado nos Correios (Melhor Envio webhook order.posted).',
    )

    logger.info('Webhook ME: pedido %s → enviado (postagem automática)', pedido.numero)
    enviar_notificacao_envio(pedido)


def _processar_entrega(pedido, data):
    """order.delivered — entregue → marca entregue + e-mail com pedido de avaliação."""
    from .models import HistoricoPedido
    from .emails import enviar_confirmacao_entrega

    if pedido.status == 'entregue':
        logger.info('Webhook ME order.delivered: pedido %s já entregue, ignorando', pedido.numero)
        return

    if pedido.status not in ('enviado', 'pagamento_confirmado', 'em_separacao'):
        logger.warning('Webhook ME order.delivered: pedido %s em status=%s inesperado',
                       pedido.numero, pedido.status)
        return

    status_anterior = pedido.status
    pedido.status = 'entregue'
    pedido.save(update_fields=['status', 'atualizado_em'])

    HistoricoPedido.objects.create(
        pedido=pedido,
        status_anterior=status_anterior,
        status_novo='entregue',
        observacao='Entrega confirmada pelos Correios (Melhor Envio webhook order.delivered).',
    )

    logger.info('Webhook ME: pedido %s → entregue (confirmação automática)', pedido.numero)
    enviar_confirmacao_entrega(pedido)
