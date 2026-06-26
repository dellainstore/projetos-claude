import base64
import hashlib
import hmac
import json
import logging
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
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


def _itens_carrinho_para_json(cart):
    return [
        {
            'produto_id':    item.get('produto_id'),
            'variacao_id':   item.get('variacao_id'),
            'nome':          item['nome'],
            'variacao_desc': item.get('variacao_desc', ''),
            'preco':         str(item['preco_decimal']),
            'quantidade':    item['quantidade'],
            'subtotal':      str(item['subtotal']),
            'imagem':        item.get('imagem', ''),
        }
        for item in cart
    ]


def _salvar_carrinho_abandonado(request, cart):
    """Persiste (ou atualiza) o snapshot do carrinho no banco para o usuario logado."""
    if not request.user.is_authenticated:
        return
    if len(cart) == 0:
        return
    try:
        from .models import CarrinhoAbandonado
        CarrinhoAbandonado.objects.update_or_create(
            cliente=request.user,
            defaults={
                'email':       request.user.email,
                'nome':        request.user.get_full_name(),
                'itens_json':  _itens_carrinho_para_json(cart),
                'total':       cart.get_total(),
                'recuperado':  False,
            },
        )
    except Exception as exc:
        logger.debug('Nao foi possivel salvar carrinho abandonado: %s', exc)


def _salvar_carrinho_abandonado_guest(request, cart, email, nome='', telefone=''):
    """Persiste (ou atualiza) snapshot do carrinho para usuario nao logado (guest)."""
    if len(cart) == 0:
        return
    try:
        from .models import CarrinhoAbandonado
        itens = _itens_carrinho_para_json(cart)
        existing = (
            CarrinhoAbandonado.objects
            .filter(cliente=None, email=email, recuperado=False)
            .order_by('-atualizado_em')
            .first()
        )
        if existing:
            existing.itens_json = itens
            existing.total = cart.get_total()
            if nome:
                existing.nome = nome
            if telefone:
                existing.telefone = telefone
            existing.recuperado = False
            existing.save(update_fields=['itens_json', 'total', 'nome', 'telefone', 'recuperado', 'atualizado_em'])
        else:
            CarrinhoAbandonado.objects.create(
                cliente=None,
                email=email,
                nome=nome,
                telefone=telefone,
                itens_json=itens,
                total=cart.get_total(),
                recuperado=False,
            )
    except Exception as exc:
        logger.debug('Nao foi possivel salvar carrinho abandonado guest: %s', exc)


def _limpar_carrinho_abandonado(request, email=None):
    """Marca o carrinho como recuperado apos checkout bem-sucedido."""
    try:
        from .models import CarrinhoAbandonado
        if request.user.is_authenticated:
            CarrinhoAbandonado.objects.filter(cliente=request.user).update(recuperado=True)
        guest_email = email or request.session.get('guest_checkout_email', '')
        if guest_email and not request.user.is_authenticated:
            CarrinhoAbandonado.objects.filter(
                cliente=None, email=guest_email, recuperado=False,
            ).update(recuperado=True)
    except Exception as exc:
        logger.debug('Nao foi possivel marcar carrinho como recuperado: %s', exc)


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

def recuperar_carrinho_abandonado(request, token):
    """Restaura na sessao os itens de um CarrinhoAbandonado a partir do token do e-mail."""
    from .models import CarrinhoAbandonado
    from apps.produtos.models import Produto, Variacao

    try:
        ca = CarrinhoAbandonado.objects.get(token=token, recuperado=False)
    except (CarrinhoAbandonado.DoesNotExist, ValueError):
        messages.info(request, 'Este link de carrinho nao esta mais disponivel.')
        return redirect('pedidos:carrinho')

    cart = Carrinho(request)
    total_itens = 0
    restaurados = 0

    for item in ca.itens:
        produto_id  = item.get('produto_id')
        variacao_id = item.get('variacao_id')
        quantidade  = int(item.get('quantidade', 1) or 1)
        if not produto_id or quantidade <= 0:
            continue
        total_itens += 1
        try:
            produto = Produto.objects.get(pk=produto_id, ativo=True)
        except Produto.DoesNotExist:
            continue
        variacao = None
        if variacao_id:
            try:
                variacao = Variacao.objects.get(pk=variacao_id, ativa=True, produto=produto)
            except Variacao.DoesNotExist:
                continue

        tamanho_antes = len(cart)
        cart.adicionar(produto, variacao=variacao, quantidade=quantidade)
        if len(cart) > tamanho_antes:
            restaurados += 1

    if restaurados == 0:
        messages.info(request, 'Os itens deste carrinho nao estao mais disponiveis.')
    elif restaurados < total_itens:
        messages.warning(
            request,
            'Alguns itens nao estao mais disponiveis e foram removidos do seu carrinho. '
            'Confira o que ainda esta disponivel e finalize sua compra.',
        )
    else:
        messages.success(request, 'Seu carrinho foi restaurado. Finalize sua compra para garantir suas pecas.')

    return redirect('pedidos:carrinho')


def carrinho(request):
    cart = Carrinho(request)
    total = cart.get_total()

    from django.core.cache import cache
    from apps.core_utils.cache_utils import LOJA_CONFIG
    config_loja = cache.get(LOJA_CONFIG)
    if config_loja is None:
        try:
            from apps.conteudo.models import ConfiguracaoLoja
            config_loja = ConfiguracaoLoja.get_config()
        except Exception:
            config_loja = None
        cache.set(LOJA_CONFIG, config_loja, 60 * 60 * 24)

    frete_meta = getattr(config_loja, 'frete_gratis_acima', None) if config_loja else None
    frete_faltante = max(Decimal('0'), frete_meta - total) if frete_meta else None

    itens_list = list(cart)

    # Produtos relacionados: mesma categoria dos itens no carrinho, excluindo os já presentes
    relacionados_carrinho = []
    try:
        from apps.produtos.models import Produto, Variacao as _Variacao
        variacao_ids = [item.get('variacao_id') for item in itens_list if item.get('variacao_id')]
        produto_ids_no_carrinho = [item.get('produto_id') for item in itens_list if item.get('produto_id')]
        if variacao_ids:
            cat_ids = list(
                _Variacao.objects
                .filter(pk__in=variacao_ids)
                .values_list('produto__categoria_id', flat=True)
                .distinct()
            )
            if cat_ids:
                relacionados_carrinho = list(
                    Produto.objects
                    .filter(ativo=True, categoria_id__in=cat_ids)
                    .exclude(pk__in=produto_ids_no_carrinho)
                    .prefetch_related('imagens')
                    .order_by('-destaque', '-criado_em')[:4]
                )
    except Exception:
        relacionados_carrinho = []

    context = {
        'carrinho':              cart,
        'itens':                 itens_list,
        'total':                 total,
        'config_loja':           config_loja,
        'frete_meta':            frete_meta,
        'frete_faltante':        frete_faltante,
        'relacionados_carrinho': relacionados_carrinho,
    }
    if itens_list:
        try:
            from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
            _sessao = obter_ou_criar_sessao(request)
            if _sessao:
                registrar_evento(_sessao, 'carrinho_visualizado', pagina_url=request.path)
        except Exception:
            pass
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

    try:
        from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
        _sessao = obter_ou_criar_sessao(request)
        if _sessao:
            _preco = variacao.preco_atual if variacao else produto.preco_atual
            registrar_evento(_sessao, 'produto_adicionado',
                             produto_slug=produto.slug,
                             produto_nome=produto.nome,
                             categoria_nome=produto.categoria.nome if produto.categoria_id else '',
                             variacao_desc=str(variacao) if variacao else '',
                             quantidade=quantidade,
                             valor_unitario=_preco,
                             valor_total=_preco * quantidade)
    except Exception:
        pass

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
                    'content_category': produto.categoria.nome if produto.categoria_id else '',
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
    item_removido = cart.carrinho.get(str(item_id), {})
    cart.remover(item_id)
    try:
        from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
        _sessao = obter_ou_criar_sessao(request)
        if _sessao:
            registrar_evento(_sessao, 'produto_removido',
                             produto_slug=item_removido.get('slug', ''),
                             produto_nome=item_removido.get('nome', ''))
    except Exception:
        pass
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
        initial['cpf']       = u.cpf
        initial['telefone']  = u.get_telefone_formatado()

        # Endereço principal salvo
        try:
            end = u.enderecos.filter(principal=True).first() or u.enderecos.first()
            if end:
                initial.update({
                    'cep':            end.cep,
                    'logradouro':     end.logradouro,
                    'numero_entrega': end.numero,
                    'complemento':    end.complemento,
                    'bairro':         end.bairro,
                    'cidade':         end.cidade,
                    'estado':         end.estado,
                })
        except Exception:
            logger.debug('Falha ao pre-preencher endereco no checkout', exc_info=True)

    if request.method == 'POST':
        form = CheckoutForm(request.POST, initial=initial)
        if form.is_valid():
            return _processar_checkout(request, form, cart)
        # Form inválido → renderiza de volta com erros
    else:
        form = CheckoutForm(initial=initial)
        try:
            from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
            _sessao = obter_ou_criar_sessao(request)
            if _sessao:
                registrar_evento(_sessao, 'checkout_iniciado', pagina_url=request.path)
        except Exception:
            pass

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

    enderecos = list(request.user.enderecos.all()) if request.user.is_authenticated else []

    cartoes_salvos = []
    if request.user.is_authenticated and cartao_habilitado:
        from apps.pagamentos.models import CartaoSalvo
        cartoes_salvos = list(CartaoSalvo.objects.filter(
            cliente=request.user, ativo=True,
        ))

    context = {
        'form':                  form,
        'itens':                 itens,
        'subtotal':              subtotal,
        'total_itens':           sum(item['quantidade'] for item in itens),
        'pagseguro_public_key':  pagseguro_public_key,
        'cartao_habilitado':     cartao_habilitado,
        'pagseguro_sandbox':     bool(settings.PAGSEGURO_SANDBOX),
        'meta_initiatecheckout_event_id': meta_initiatecheckout_event_id,
        'enderecos':             enderecos,
        'cartoes_salvos':        cartoes_salvos,
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
        logger.warning('Falha ao enviar evento Meta CAPI InitiateCheckout', exc_info=True)
    return render(request, 'checkout/index.html', context)


def _ler_consentimento(request):
    """Le o cookie della_consent e retorna (marketing, analytics) como booleans.

    Persistido no pedido para permitir o disparo server-side do purchase (Meta
    CAPI / GA4 MP) quando o pagamento confirma fora do browser (ex: PIX/webhook),
    respeitando a escolha LGPD que a cliente fez no momento da compra.
    """
    raw = request.COOKIES.get('della_consent', '')
    if not raw:
        return False, False
    try:
        from urllib.parse import unquote
        data = json.loads(unquote(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, False
    return bool(data.get('marketing')), bool(data.get('analytics'))


def _ler_utms_atribuicao(request):
    """
    Le UTMs dos parametros GET da requisicao atual e, como fallback, do cookie
    della_attr gravado pelo della.js quando o usuario chegou via link com UTMs.

    O cookie permite recuperar a atribuicao mesmo quando o checkout ocorre em
    sessao diferente da visita original (localStorage nao chega ao servidor).

    Retorna dict com os campos disponiveis.
    """
    params = request.GET
    utms = {}
    for key in ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id'):
        val = (params.get(key) or '').strip()[:200]
        if val:
            utms[key] = val

    # Fallback: cookie della_attr gravado pelo JS na visita original
    try:
        import json as _json
        from urllib.parse import unquote as _unq
        raw_attr = request.COOKIES.get('della_attr', '')
        if raw_attr:
            attr = _json.loads(_unq(raw_attr))
            for key in ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id'):
                if key not in utms and attr.get(key):
                    utms[key] = str(attr[key])[:200]
    except Exception:
        pass

    return utms


def _ler_gclid(request):
    """Extrai o gclid do cookie _gcl_aw (formato GCL.<ts>.<gclid>) ou della_attr."""
    raw = request.COOKIES.get('_gcl_aw', '').strip()
    if not raw:
        raw = request.GET.get('gclid', '').strip()
    if raw and raw.startswith('GCL.'):
        partes = raw.split('.', 2)
        return partes[2] if len(partes) == 3 else ''
    if raw:
        return raw[:300]
    # Fallback: della_attr cookie gravado pelo JS quando gclid estava na URL
    try:
        import json as _json
        from urllib.parse import unquote as _unq
        raw_attr = request.COOKIES.get('della_attr', '')
        if raw_attr:
            val = str(_json.loads(_unq(raw_attr)).get('gclid', '') or '').strip()
            if val:
                return val[:300]
    except Exception:
        pass
    return ''


def _ler_fbclid(request):
    """Extrai fbclid do cookie _fbc, della_attr ou da URL."""
    fbc = request.COOKIES.get('_fbc', '').strip()
    if fbc and '.' in fbc:
        partes = fbc.rsplit('.', 1)
        return partes[1][:300] if len(partes) == 2 else ''
    fbclid_url = request.GET.get('fbclid', '').strip()
    if fbclid_url:
        return fbclid_url[:300]
    # Fallback: della_attr cookie gravado pelo JS quando fbclid estava na URL
    try:
        import json as _json
        from urllib.parse import unquote as _unq
        raw_attr = request.COOKIES.get('della_attr', '')
        if raw_attr:
            val = str(_json.loads(_unq(raw_attr)).get('fbclid', '') or '').strip()
            if val:
                return val[:300]
    except Exception:
        pass
    return ''


def _ler_ga_client_id(request):
    """Extrai o client_id do GA4 do cookie _ga (formato GA1.1.<id>.<ts>).

    Usado no disparo server-side (Measurement Protocol) para manter a mesma
    identidade/atribuicao do evento client-side e a dedup por transaction_id.
    """
    raw = request.COOKIES.get('_ga', '').strip()
    if not raw:
        return ''
    partes = raw.split('.')
    if len(partes) >= 4:
        return f'{partes[-2]}.{partes[-1]}'
    return ''


def _ler_ga_session_id(request):
    """Extrai o session_id do GA4 do cookie _ga_<STREAM_ID>.

    O session_id e necessario no Measurement Protocol para vincular o evento
    purchase a uma sessao existente, o que permite ao GA4 atribuir o canal de
    origem correto. Sem ele o evento aparece como 'Unassigned'.

    Cookie: _ga_STREAMID (ex: _ga_ABC123DEF para GA_MEASUREMENT_ID=G-ABC123DEF)
    Formato do valor: GS1.1.<session_id>.<session_count>.<last_ts>...
    """
    from django.conf import settings as _settings
    measurement_id = getattr(_settings, 'GA_MEASUREMENT_ID', '') or ''
    if not measurement_id.startswith('G-'):
        return ''
    stream_id = measurement_id[2:]
    cookie_name = f'_ga_{stream_id}'
    raw = request.COOKIES.get(cookie_name, '').strip()
    if not raw:
        return ''
    partes = raw.split('.')
    # Formato GS1.1.<session_id>... — session_id esta no indice 2
    if len(partes) >= 3:
        session_id = partes[2]
        if session_id.isdigit():
            return session_id
    return ''


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
    eh_retirada_loja = (cd.get('opcao_frete') or '').strip() == 'retirada_loja'

    calculo = CalculadorPedido().calcular(
        subtotal=subtotal,
        cupom_codigo=cd.get('cupom_codigo', ''),
        cpf=cd.get('cpf', ''),
        valor_frete=frete,
        vendedor_codigo=cd.get('codigo_vendedor_codigo', ''),
        cliente=request.user if request.user.is_authenticated else None,
    )
    cupom_obj         = calculo.cupom_obj
    cupom_emitido_obj = calculo.cupom_emitido_obj
    vendedor_obj      = calculo.vendedor_obj
    desconto          = calculo.desconto
    total             = calculo.total

    # Campo enviado pelo SDK PagSeguro JS (apenas para cartão novo)
    encrypted_card   = request.POST.get('pagseguro_card_encrypted', '').strip()
    # ID de cartão já salvo (quando cliente seleciona um cartão da carteira)
    cartao_salvo_id  = request.POST.get('cartao_salvo_id', '').strip()
    # Checkbox "salvar cartão para compras futuras"
    salvar_cartao    = request.POST.get('salvar_cartao') == 'on'

    # Snapshot de consentimento + client_id + session_id do GA4 para o disparo
    # server-side do purchase (ex: PIX confirmado no webhook, sem browser).
    # Ver _ler_consentimento. O session_id e necessario no Measurement Protocol
    # para vincular o evento a uma sessao e evitar "Unassigned" no GA4.
    consent_marketing, consent_analytics = _ler_consentimento(request)
    ga_client_id  = _ler_ga_client_id(request)
    ga_session_id = _ler_ga_session_id(request)

    # Captura de atribuicao de campanha — persistida no pedido para analise de ROI
    utms = _ler_utms_atribuicao(request)
    gclid_capturado  = _ler_gclid(request)
    fbclid_capturado = _ler_fbclid(request)

    if forma_pagamento == 'cartao_credito' and not encrypted_card and not cartao_salvo_id:
        messages.error(request, 'Dados do cartão não recebidos. Tente novamente.')
        return redirect('pedidos:checkout')

    # Valida cartão salvo pertence ao usuário logado
    cartao_salvo_obj = None
    if cartao_salvo_id and request.user.is_authenticated:
        from apps.pagamentos.models import CartaoSalvo
        try:
            cartao_salvo_obj = CartaoSalvo.objects.get(
                pk=int(cartao_salvo_id),
                cliente=request.user,
                ativo=True,
            )
            if cartao_salvo_obj.esta_vencido:
                messages.error(request, f'O cartão {cartao_salvo_obj.descricao} está vencido. Por favor, use outro cartão.')
                return redirect('pedidos:checkout')
        except (CartaoSalvo.DoesNotExist, ValueError):
            messages.error(request, 'Cartão selecionado inválido. Tente novamente.')
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
                retirada_loja         = eh_retirada_loja,
                transportadora        = 'Retirada na Loja' if eh_retirada_loja else cd.get('servico_frete_nome', ''),
                frete_servico_id      = '' if eh_retirada_loja else (cd.get('opcao_frete') or '').strip(),
                frete_prazo_dias      = None if eh_retirada_loja else (cd.get('prazo_frete') or None),
                observacao_cliente    = cd.get('observacao', ''),
                gateway               = 'pagseguro' if forma_pagamento == 'cartao_credito' else '',
                cupom                 = cupom_obj,
                cupom_codigo          = cupom_emitido_obj.codigo if cupom_emitido_obj else (cupom_obj.codigo if cupom_obj else ''),
                codigo_vendedor       = vendedor_obj,
                codigo_vendedor_str   = vendedor_obj.codigo if vendedor_obj else '',
                consentimento_marketing = consent_marketing,
                consentimento_analytics = consent_analytics,
                ga_client_id  = ga_client_id,
                ga_session_id = ga_session_id,
                utm_source   = utms.get('utm_source', ''),
                utm_medium   = utms.get('utm_medium', ''),
                utm_campaign = utms.get('utm_campaign', ''),
                utm_content  = utms.get('utm_content', ''),
                utm_term     = utms.get('utm_term', ''),
                utm_id       = utms.get('utm_id', ''),
                gclid        = gclid_capturado,
                fbclid       = fbclid_capturado,
            )
            pedido.full_clean()
            pedido.save()

            criar_itens_pedido(pedido, cart)

            # Registra eventos analytics: 1 por item (para produtos mais vendidos) e 1 de total
            try:
                from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
                _sessao = obter_ou_criar_sessao(request)
                if _sessao:
                    for _item in pedido.itens.select_related('produto').all():
                        registrar_evento(_sessao, 'pedido_finalizado',
                                         produto_slug=_item.produto.slug if _item.produto_id else '',
                                         produto_nome=_item.nome_produto,
                                         variacao_desc=_item.variacao_desc,
                                         quantidade=_item.quantidade,
                                         valor_unitario=_item.preco_unitario,
                                         valor_total=_item.subtotal)
                    registrar_evento(_sessao, 'pedido_finalizado',
                                     pedido_numero=pedido.numero,
                                     valor_total=pedido.total,
                                     forma_pagamento=pedido.forma_pagamento)
            except Exception:
                pass

            # ── Processamento de cartão via PagSeguro ─────────────────────────
            if forma_pagamento == 'cartao_credito':
                from apps.pagamentos.services.pagseguro import (
                    criar_ordem_cartao, criar_ordem_cartao_token,
                    status_interno, mensagem_recusa,
                )

                if cartao_salvo_obj:
                    # Usa token do cartão já salvo — sem encrypted_card
                    resultado = criar_ordem_cartao_token(pedido, cartao_salvo_obj.token_pagbank, parcelas)
                else:
                    # Cartão novo: solicita store=True se o cliente marcou o checkbox
                    resultado = criar_ordem_cartao(pedido, encrypted_card, parcelas, store=salvar_cartao)

                charges      = resultado.get('charges', [])
                charge       = charges[0] if charges else {}
                charge_status = (charge.get('status') or '').upper()
                gateway_order_id = resultado.get('id', '')

                if charge_status == 'DECLINED':
                    raise _PagamentoRecusado(mensagem_recusa(charge))

                # PAID, AUTHORIZED ou IN_ANALYSIS → pedido criado
                novo_status = status_interno(charge_status) or 'aguardando_pagamento'
                if novo_status != pedido.status:
                    from apps.pedidos.models import HistoricoPedido
                    HistoricoPedido.objects.create(
                        pedido=pedido,
                        status_anterior=pedido.status,
                        status_novo=novo_status,
                        observacao=f'PagSeguro checkout: charge {gateway_order_id} → {charge_status}',
                    )
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

    # Salvar cartão tokenizado (apenas se checkout teve sucesso e cliente pediu)
    if (
        forma_pagamento == 'cartao_credito'
        and salvar_cartao
        and not cartao_salvo_obj
        and request.user.is_authenticated
    ):
        try:
            from apps.pagamentos.services.pagseguro import salvar_cartao_do_charge
            charges_resp = resultado.get('charges', [])
            if charges_resp:
                salvar_cartao_do_charge(request.user, charges_resp[0])
        except Exception as exc:
            logger.warning('Não foi possível salvar cartão para %s: %s', request.user.email, exc)

    if cupom_obj:
        from .models import Cupom as _Cupom
        _Cupom.objects.filter(pk=cupom_obj.pk).update(vezes_usado=models.F('vezes_usado') + 1)

    if cupom_emitido_obj:
        from django.utils import timezone as _tz
        cupom_emitido_obj.usado_em = _tz.now()
        cupom_emitido_obj.pedido = pedido
        cupom_emitido_obj.save(update_fields=['usado_em', 'pedido'])

    cart.limpar()
    _limpar_carrinho_abandonado(request, email=cd.get('email', ''))

    request.session['ultimo_pedido'] = pedido.numero
    # Flag de rastreamento: garante que o evento purchase (GA4 + Meta) seja
    # renderizado apenas na primeira exibicao da confirmacao pos-checkout.
    # Consumida (removida) no primeiro render em confirmacao_pedido, evitando
    # disparo duplicado se a cliente reabrir a pagina depois (mesmo em outro
    # dispositivo, onde sessionStorage nao protege).
    request.session['rastrear_purchase'] = pedido.numero
    pedidos_guest = request.session.get('pedidos_guest', [])
    if pedido.numero not in pedidos_guest:
        pedidos_guest.append(pedido.numero)
        request.session['pedidos_guest'] = pedidos_guest[-20:]

    # Newsletter opt-in no checkout (guest ou logado que marcou a caixa)
    if cd.get('newsletter_optin'):
        try:
            from apps.produtos.models import NewsletterInscricao
            from django.db import IntegrityError as _IntegrityError
            try:
                NewsletterInscricao.objects.create(email=pedido.email)
            except _IntegrityError:
                pass  # já inscrito
            if request.user.is_authenticated and not request.user.recebe_newsletter:
                request.user.__class__.objects.filter(pk=request.user.pk).update(recebe_newsletter=True)
        except Exception as exc:
            logger.warning('Newsletter opt-in no checkout falhou: %s', exc)

    try:
        from .emails import enviar_confirmacao_pedido, enviar_confirmacao_pagamento
        enviar_confirmacao_pedido(pedido)
        if pedido.status == 'pagamento_confirmado':
            enviar_confirmacao_pagamento(pedido)
    except Exception as exc:
        logger.warning('Não foi possível enviar e-mail de confirmação: %s', exc)

    # Envio ao Bling — fora do atomic para não afetar o checkout se o Bling falhar
    try:
        from apps.bling.services import enviar_pedido_bling
        enviar_pedido_bling(pedido)
    except Exception as exc:
        logger.warning('Bling: não foi possível enviar pedido %s: %s', pedido.numero, exc)

    # Purchase (Meta CAPI) so quando o pagamento ja esta confirmado no checkout
    # (cartao PAID/AUTHORIZED). Para PIX e cartao em analise, o webhook do PagBank
    # dispara ao confirmar. Flag capi_purchase_enviado garante idempotencia: o
    # webhook nao re-envia se o checkout ja disparou (evita duplo CAPI).
    if pedido.status == 'pagamento_confirmado' and not pedido.capi_purchase_enviado:
        try:
            enviado = enviar_evento_purchase(pedido, request)
            if enviado:
                from .models import Pedido as _Pedido
                _Pedido.objects.filter(pk=pedido.pk).update(capi_purchase_enviado=True)
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

    # Dispara o purchase client-side (Pixel + GA4) apenas na primeira exibicao
    # pos-checkout E somente com o pagamento ja confirmado:
    #  - cartao aprovado: confirma no checkout, dispara neste primeiro render;
    #  - PIX: 1o render fica aguardando_pagamento (nao dispara, flag preservada);
    #    quando o polling detecta o pagamento a pagina recarrega ja paga e dispara.
    # A flag so e consumida quando o evento realmente renderiza, evitando perder
    # o PIX e impedindo re-disparo em revisitas (link, Meus Pedidos, outro device).
    # Para PIX pago apos fechar a pagina, o webhook cobre via Meta CAPI + GA4 MP.
    ja_pago = pedido.status == 'pagamento_confirmado'
    disparar_tracking = ja_pago and request.session.get('rastrear_purchase') == numero
    if disparar_tracking:
        del request.session['rastrear_purchase']
        request.session.modified = True

    context = {
        'pedido':            pedido,
        'itens':             pedido.itens.select_related('produto').all(),
        'pix_qrcode':        pix_qrcode,
        'pix_payload':       pix_payload,
        'pix_via':           pix_via,
        'disparar_tracking': disparar_tracking,
    }
    return render(request, 'checkout/confirmacao.html', context)


# ─── Frete ────────────────────────────────────────────────────────────────────

def validar_cupom(request):
    """AJAX: valida cupom e retorna desconto para o subtotal enviado.

    Aceita tanto cupons manuais (Cupom com origem=manual) quanto cupons emitidos
    individualmente (CupomEmitido — newsletter, primeira_compra, etc.).
    """
    from .models import Cupom, CupomEmitido
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

    cliente = request.user if request.user.is_authenticated else None

    cupom = None
    codigo_retorno = codigo
    try:
        emitido = CupomEmitido.objects.select_related('cupom_template').get(codigo__iexact=codigo)
        ok, motivo = emitido.esta_valido(cpf=cpf, cliente=cliente)
        if not ok:
            try:
                from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
                _sessao = obter_ou_criar_sessao(request)
                if _sessao:
                    registrar_evento(_sessao, 'cupom_invalido', cupom_codigo=codigo[:50])
            except Exception:
                pass
            return JsonResponse({'status': 'erro', 'erro': motivo})
        cupom = emitido.cupom_template
        codigo_retorno = emitido.codigo
    except CupomEmitido.DoesNotExist:
        try:
            cupom = Cupom.objects.get(codigo__iexact=codigo, ativo=True, origem='manual')
        except Cupom.DoesNotExist:
            try:
                from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
                _sessao = obter_ou_criar_sessao(request)
                if _sessao:
                    registrar_evento(_sessao, 'cupom_invalido', cupom_codigo=codigo[:50])
            except Exception:
                pass
            return JsonResponse({'status': 'erro', 'erro': 'Cupom inválido.'})
        ok, motivo = cupom.esta_valido(cpf=cpf)
        if not ok:
            try:
                from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
                _sessao = obter_ou_criar_sessao(request)
                if _sessao:
                    registrar_evento(_sessao, 'cupom_invalido', cupom_codigo=codigo[:50])
            except Exception:
                pass
            return JsonResponse({'status': 'erro', 'erro': motivo})
        codigo_retorno = cupom.codigo

    desconto = cupom.calcular_desconto(subtotal)
    if cupom.tipo == 'percentual':
        descricao = f'{cupom.valor:.0f}% de desconto'
    else:
        v = f'{cupom.valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        descricao = f'R$ {v} de desconto'

    try:
        from apps.analytics.services import obter_ou_criar_sessao, registrar_evento
        _sessao = obter_ou_criar_sessao(request)
        if _sessao:
            registrar_evento(_sessao, 'cupom_aplicado', cupom_codigo=codigo_retorno[:50])
    except Exception:
        pass

    return JsonResponse({
        'status':    'ok',
        'codigo':    codigo_retorno,
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

    lista = [
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
    ]

    lista.append({
        'id':        'retirada_loja',
        'nome':      'Retirar na Loja',
        'empresa':   "D'ELLA",
        'preco':     '0',
        'prazo':     0,
        'descricao': 'Disponível a partir de 2h após confirmação do pagamento',
    })

    return JsonResponse({'status': 'ok', 'opcoes': lista})


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


# ─── Captura de e-mail guest no checkout ───────────────────────────────────────

@require_POST
def capturar_email_checkout(request):
    """
    AJAX: Registra o e-mail do guest assim que ele digita no checkout,
    salvando snapshot do carrinho como CarrinhoAbandonado para envio futuro.
    Retorna JSON {status: 'ok'} ou {status: 'erro', erro: '...'}.
    """
    import json as _json
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError as _DjValidation

    try:
        body = _json.loads(request.body)
    except Exception:
        body = request.POST

    email    = (body.get('email') or '').strip().lower()
    nome     = (body.get('nome') or '').strip()[:240]
    telefone = (body.get('telefone') or '').strip()[:20]

    if not email:
        return JsonResponse({'status': 'erro', 'erro': 'E-mail obrigatorio.'})

    try:
        validate_email(email)
    except _DjValidation:
        return JsonResponse({'status': 'erro', 'erro': 'E-mail invalido.'})

    cart = Carrinho(request)
    if len(cart) > 0:
        request.session['guest_checkout_email'] = email
        _salvar_carrinho_abandonado_guest(request, cart, email, nome, telefone)

    return JsonResponse({'status': 'ok'})
