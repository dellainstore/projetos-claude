from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db.models import Q, Avg, Count
from django.conf import settings

from apps.core_utils.cache_utils import (
    MENU_CATEGORIAS, HOME_BANNERS, HOME_MINI_BANNERS, HOME_LOOK,
    HOME_DEPOIMENTOS, HOME_DESTAQUES, LOJA_CONFIG, GUIA_TABELAS,
    _key_pagina, _key_relacionados, _key_tabela_medidas,
)


def _get_instagram_posts() -> list:
    """Retorna posts do Instagram marcados como ativos no admin."""
    try:
        from apps.conteudo.models import InstagramPost
        return list(InstagramPost.objects.filter(ativo=True).order_by('ordem', '-timestamp')[:12])
    except Exception:
        return []


def homepage(request):
    from apps.produtos.models import Categoria, Produto, Avaliacao
    from apps.conteudo.models import BannerPrincipal, MiniBanner, LookDaSemana

    # Produtos em destaque (cache 2h — muda ao cadastrar/editar produto)
    produtos_destaque = cache.get(HOME_DESTAQUES)
    if produtos_destaque is None:
        try:
            produtos_destaque = list(
                Produto.objects.filter(ativo=True, destaque=True).prefetch_related('imagens')[:8]
            )
        except Exception:
            produtos_destaque = []
        cache.set(HOME_DESTAQUES, produtos_destaque, 60 * 60 * 2)

    # Depoimentos (cache 6h — moderação manual; select_related evita N+1 no template)
    depoimentos = cache.get(HOME_DEPOIMENTOS)
    if depoimentos is None:
        try:
            depoimentos = list(
                Avaliacao.objects.filter(aprovada=True)
                .select_related('produto')
                .order_by('-criada_em')[:3]
            )
        except Exception:
            depoimentos = []
        cache.set(HOME_DEPOIMENTOS, depoimentos, 60 * 60 * 6)

    # Banners do hero (cache 1h — invalidado ao salvar no admin)
    banners = cache.get(HOME_BANNERS)
    if banners is None:
        try:
            banners = list(BannerPrincipal.objects.filter(ativo=True).order_by('ordem'))
        except Exception:
            banners = []
        cache.set(HOME_BANNERS, banners, 60 * 60)

    # Mini-banners (cache 1h — invalidado ao salvar no admin)
    mini_banners = cache.get(HOME_MINI_BANNERS)
    if mini_banners is None:
        try:
            mini_banners = list(MiniBanner.objects.filter(ativo=True).order_by('posicao'))
        except Exception:
            mini_banners = []
        cache.set(HOME_MINI_BANNERS, mini_banners, 60 * 60)

    # Look da semana (cache 1h — invalidado ao salvar no admin)
    look_obj = cache.get(HOME_LOOK)
    if look_obj is None:
        try:
            look_obj = LookDaSemana.objects.filter(ativo=True).select_related(
                'produto_ponto1', 'produto_ponto2', 'produto_ponto3'
            ).prefetch_related(
                'produto_ponto1__imagens', 'produto_ponto2__imagens', 'produto_ponto3__imagens'
            ).first()
        except Exception:
            look_obj = None
        cache.set(HOME_LOOK, look_obj, 60 * 60)

    look_produtos = []
    if look_obj:
        look_produtos = [p for p in [
            look_obj.produto_ponto1,
            look_obj.produto_ponto2,
            look_obj.produto_ponto3,
        ] if p and p.ativo]

    wishlist_ids = set()
    if request.user.is_authenticated:
        try:
            wishlist_ids = set(request.user.wishlist_set.values_list('produto_id', flat=True))
        except Exception:
            pass

    context = {
        'produtos_destaque':      produtos_destaque,
        'depoimentos':            depoimentos,
        'banners':                banners,
        'mini_banners':           mini_banners,
        'look_obj':               look_obj,
        'look_produtos':          look_produtos,
        'wishlist_ids':           wishlist_ids,
        'instagram_posts':        _get_instagram_posts(),
        'WHATSAPP_NUMBER_1':      settings.WHATSAPP_NUMBER_1,
        'WHATSAPP_NUMBER_2':      settings.WHATSAPP_NUMBER_2,
    }
    return render(request, 'home/index.html', context)


def loja(request, categoria_slug=None):
    from apps.produtos.models import Categoria, Produto

    # Sidebar — reutiliza o mesmo cache do menu principal (invalidado junto)
    categorias = cache.get(MENU_CATEGORIAS)
    if categorias is None:
        categorias = list(
            Categoria.objects
            .filter(ativa=True, parent__isnull=True)
            .prefetch_related('subcategorias')
            .order_by('ordem', 'nome')
        )
        cache.set(MENU_CATEGORIAS, categorias, 60 * 60 * 4)
    categoria_ativa = None

    produtos_qs = Produto.objects.filter(ativo=True).prefetch_related('imagens', 'variacoes')

    if categoria_slug:
        categoria_ativa = get_object_or_404(Categoria, slug=categoria_slug, ativa=True)
        # Se é uma categoria-mãe, inclui também os produtos das subcategorias
        sub_ids = list(categoria_ativa.subcategorias.filter(ativa=True).values_list('id', flat=True))
        if sub_ids:
            from django.db.models import Q as _Q
            produtos_qs = produtos_qs.filter(
                _Q(categoria=categoria_ativa) | _Q(categoria_id__in=sub_ids)
            )
        else:
            produtos_qs = produtos_qs.filter(categoria=categoria_ativa)

    # Filtro de busca
    q = request.GET.get('q', '').strip()
    if q:
        produtos_qs = produtos_qs.filter(
            Q(nome__icontains=q) | Q(descricao__icontains=q)
        )

    # Filtro de preço
    preco_min = request.GET.get('preco_min', '')
    preco_max = request.GET.get('preco_max', '')
    if preco_min:
        try:
            produtos_qs = produtos_qs.filter(preco__gte=float(preco_min))
        except ValueError:
            pass
    if preco_max:
        try:
            produtos_qs = produtos_qs.filter(preco__lte=float(preco_max))
        except ValueError:
            pass

    # Filtro novidades / promoção
    apenas_novos = request.GET.get('novo') == '1'
    apenas_promo = request.GET.get('promo') == '1'
    if apenas_novos:
        produtos_qs = produtos_qs.filter(novo=True)
    if apenas_promo:
        produtos_qs = produtos_qs.exclude(preco_promocional__isnull=True)

    # Ordenação
    ordem = request.GET.get('ordem', 'relevancia')
    if ordem == 'menor_preco':
        produtos_qs = produtos_qs.order_by('preco')
    elif ordem == 'maior_preco':
        produtos_qs = produtos_qs.order_by('-preco')
    elif ordem == 'novidades':
        produtos_qs = produtos_qs.order_by('-criado_em')
    else:
        produtos_qs = produtos_qs.order_by('ordem', '-destaque', '-criado_em')

    # Paginação
    paginator = Paginator(produtos_qs, 24)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    wishlist_ids = set()
    if request.user.is_authenticated:
        try:
            wishlist_ids = set(request.user.wishlist_set.values_list('produto_id', flat=True))
        except Exception:
            pass

    context = {
        'categorias':      categorias,
        'categoria_ativa': categoria_ativa,
        'page_obj':        page_obj,
        'total_produtos':  paginator.count,
        'q':               q,
        'preco_min':       preco_min,
        'preco_max':       preco_max,
        'apenas_novos':    apenas_novos,
        'apenas_promo':    apenas_promo,
        'ordem':           ordem,
        'wishlist_ids':    wishlist_ids,
    }
    return render(request, 'produtos/loja.html', context)


def detalhe_produto(request, slug):
    from apps.produtos.models import Produto, Avaliacao

    produto = get_object_or_404(
        Produto.objects.prefetch_related('imagens', 'variacoes', 'avaliacoes'),
        slug=slug,
        ativo=True,
    )

    import json as _json
    imagens = produto.imagens.order_by('-principal', 'ordem')

    # Tamanhos únicos (sem repetir o mesmo tamanho para cada cor)
    variacoes_tamanho = list(
        produto.variacoes
        .filter(ativa=True, tamanho__isnull=False)
        .values('tamanho__id', 'tamanho__nome', 'tamanho__ordem')
        .distinct()
        .order_by('tamanho__ordem', 'tamanho__nome')
    )

    # Cores únicas — deduplica por cor__id em Python para garantir sem repetição
    _cores_raw = (
        produto.variacoes
        .filter(ativa=True, cor__isnull=False)
        .values('cor__id', 'cor__nome', 'cor__codigo_hex', 'cor__codigo_hex_secundario')
        .order_by('cor__ordem', 'cor__nome')
    )
    _vistas = set()
    variacoes_cor = []
    for c in _cores_raw:
        if c['cor__id'] not in _vistas:
            _vistas.add(c['cor__id'])
            variacoes_cor.append(c)

    # Todas as variações ativas — usadas pelo mapa JS
    variacoes_todas = list(
        produto.variacoes
        .filter(ativa=True)
        .select_related('cor', 'tamanho')
        .order_by('cor__ordem', 'cor__nome', 'tamanho__ordem', 'tamanho__nome')
    )

    # Mapa JSON: "{cor_id}_{tam_id}" → {id, disponivel}
    # Permite o JS encontrar a variação correta ao selecionar cor + tamanho
    variacoes_map = {}
    for v in variacoes_todas:
        key = f"{v.cor_id or 'null'}_{v.tamanho_id or 'null'}"
        variacoes_map[key] = {'id': v.pk, 'disponivel': v.disponivel}
    variacoes_json = _json.dumps(variacoes_map)
    avaliacoes   = produto.avaliacoes.filter(aprovada=True).order_by('-criada_em')[:10]

    media_notas  = avaliacoes.aggregate(media=Avg('nota'))['media'] or 0
    total_aval   = produto.avaliacoes.filter(aprovada=True).count()

    # Produtos relacionados — cache por categoria (3h)
    _cache_rel = _key_relacionados(produto.categoria_id)
    relacionados = cache.get(_cache_rel)
    if relacionados is None:
        relacionados = list(
            Produto.objects
            .filter(ativo=True, categoria=produto.categoria)
            .exclude(pk=produto.pk)
            .prefetch_related('imagens')
            .order_by('-destaque', '-criado_em')[:4]
        )
        cache.set(_cache_rel, relacionados, 60 * 60 * 3)

    na_wishlist = False
    if request.user.is_authenticated:
        try:
            na_wishlist = request.user.wishlist_set.filter(produto=produto).exists()
        except Exception:
            pass

    # Tabela de medidas — cache 12h por categoria
    _cache_med = _key_tabela_medidas(produto.categoria_id)
    tabela_medidas = cache.get(_cache_med)
    if tabela_medidas is None:
        try:
            from apps.produtos.models import TabelaMedidas
            tabela_medidas = (
                TabelaMedidas.objects.filter(ativo=True, categoria=produto.categoria).first()
                or TabelaMedidas.objects.filter(ativo=True, categoria__isnull=True).first()
            )
        except Exception:
            tabela_medidas = None
        cache.set(_cache_med, tabela_medidas, 60 * 60 * 12)

    # Configuração da loja (frete grátis) — cache 24h
    config_loja = cache.get(LOJA_CONFIG)
    if config_loja is None:
        try:
            from apps.conteudo.models import ConfiguracaoLoja
            config_loja = ConfiguracaoLoja.get_config()
        except Exception:
            config_loja = None
        cache.set(LOJA_CONFIG, config_loja, 60 * 60 * 24)

    # Mapa cor_id → índice da imagem na galeria (para troca de foto ao clicar na bolinha)
    fotos_cor_map = {}
    try:
        from apps.produtos.models import ProdutoCorFoto
        imagens_list = list(imagens)
        imagem_id_para_idx = {img.pk: idx for idx, img in enumerate(imagens_list)}
        for pcf in ProdutoCorFoto.objects.filter(produto=produto).select_related('imagem'):
            if pcf.imagem_id and pcf.imagem_id in imagem_id_para_idx:
                fotos_cor_map[str(pcf.cor_id)] = imagem_id_para_idx[pcf.imagem_id]
    except Exception:
        pass
    fotos_cor_json = _json.dumps(fotos_cor_map)

    context = {
        'produto':            produto,
        'imagens':            imagens,
        'variacoes_tamanho':  variacoes_tamanho,
        'variacoes_cor':      variacoes_cor,
        'variacoes_todas':    variacoes_todas,
        'variacoes_json':     variacoes_json,
        'fotos_cor_json':     fotos_cor_json,
        'avaliacoes':         avaliacoes,
        'media_notas':        round(media_notas, 1),
        'total_aval':         total_aval,
        'relacionados':       relacionados,
        'na_wishlist':        na_wishlist,
        'tabela_medidas':     tabela_medidas,
        'config_loja':        config_loja,
    }
    return render(request, 'produtos/detalhe.html', context)


def busca(request):
    from apps.produtos.models import Produto

    q = request.GET.get('q', '').strip()
    resultados = []

    if q:
        resultados = (
            Produto.objects
            .filter(ativo=True)
            .filter(Q(nome__icontains=q) | Q(descricao__icontains=q) | Q(categoria__nome__icontains=q))
            .prefetch_related('imagens')
            .order_by('-destaque', '-criado_em')[:48]
        )

    context = {'q': q, 'resultados': resultados}
    return render(request, 'produtos/busca.html', context)


@login_required
@require_POST
def toggle_wishlist(request, produto_id):
    from apps.produtos.models import Produto
    produto = get_object_or_404(Produto, pk=produto_id, ativo=True)

    try:
        from apps.usuarios.models import Wishlist
        obj, criado = Wishlist.objects.get_or_create(cliente=request.user, produto=produto)
        if not criado:
            obj.delete()
            return JsonResponse({'status': 'ok', 'na_wishlist': False})
        return JsonResponse({'status': 'ok', 'na_wishlist': True})
    except Exception:
        return JsonResponse({'status': 'ok', 'na_wishlist': False})


@login_required
def wishlist(request):
    try:
        from apps.usuarios.models import Wishlist
        itens = Wishlist.objects.filter(cliente=request.user).select_related('produto').prefetch_related('produto__imagens')
    except Exception:
        itens = []
    return render(request, 'produtos/wishlist.html', {'itens': itens})


def _pagina_estatica(request, slug, template):
    """Helper: carrega PaginaEstatica do banco; fallback para template estático. Cache 6h."""
    _cache_key = _key_pagina(slug)
    pagina = cache.get(_cache_key)
    if pagina is None:
        try:
            from apps.conteudo.models import PaginaEstatica
            pagina = PaginaEstatica.objects.filter(slug=slug, ativo=True).first()
        except Exception:
            pagina = None
        cache.set(_cache_key, pagina, 60 * 60 * 6)
    return render(request, template, {'pagina': pagina})


def sobre(request):
    return _pagina_estatica(request, 'sobre', 'home/sobre.html')


def contato(request):
    from apps.core_utils.sanitize import sanitize_text
    import json as _json

    if request.method == 'POST':
        nome      = sanitize_text(request.POST.get('nome', ''), max_length=100)
        email     = sanitize_text(request.POST.get('email', ''), max_length=254).lower()
        telefone  = sanitize_text(request.POST.get('telefone', ''), max_length=20)
        mensagem  = sanitize_text(request.POST.get('mensagem', ''), max_length=1000)

        if not nome or not email or not mensagem:
            return render(request, 'home/contato.html', {
                'erro': 'Preencha nome, e-mail e mensagem.',
                'nome': nome, 'email': email, 'telefone': telefone, 'mensagem': mensagem,
            })

        # Tenta enviar e-mail; se falhar, registra mas não expõe o erro ao usuário
        try:
            from django.core.mail import send_mail
            from django.conf import settings as _settings
            corpo = f'Nome: {nome}\nE-mail: {email}\nTelefone: {telefone}\n\nMensagem:\n{mensagem}'
            send_mail(
                subject=f'Contato pelo site — {nome}',
                message=corpo,
                from_email=_settings.EMAIL_HOST_USER,
                recipient_list=[_settings.EMAIL_HOST_USER],
                fail_silently=True,
            )
        except Exception:
            pass

        return render(request, 'home/contato.html', {'enviado': True})

    return render(request, 'home/contato.html')


def politica_privacidade(request):
    return _pagina_estatica(request, 'politica_privacidade', 'home/politica_privacidade.html')


def trocas_devolucoes(request):
    return _pagina_estatica(request, 'trocas_devolucoes', 'home/trocas_devolucoes.html')


def termos_uso(request):
    return _pagina_estatica(request, 'termos_uso', 'home/termos_uso.html')


def perguntas_frequentes(request):
    return _pagina_estatica(request, 'perguntas_frequentes', 'home/perguntas_frequentes.html')


def meios_pagamento(request):
    return _pagina_estatica(request, 'meios_pagamento', 'home/meios_pagamento.html')


def guia_tamanhos(request):
    """Exibe o guia de tamanhos. Cache 24h — raramente muda."""
    tabelas = cache.get(GUIA_TABELAS)
    if tabelas is None:
        from apps.produtos.models import TabelaMedidas
        tabelas = list(TabelaMedidas.objects.filter(ativo=True).order_by('nome'))
        cache.set(GUIA_TABELAS, tabelas, 60 * 60 * 24)
    return render(request, 'home/guia_tamanhos.html', {'tabelas': tabelas})


@require_POST
def newsletter_signup(request):
    import json
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.db import IntegrityError
    from apps.core_utils.sanitize import sanitize_text
    from apps.produtos.models import NewsletterInscricao

    try:
        data  = json.loads(request.body)
        email = sanitize_text(data.get('email', ''), max_length=254).lower().strip()

        if not email:
            return JsonResponse({'status': 'erro', 'erro': 'E-mail inválido.'})

        try:
            validate_email(email)
        except DjangoValidationError:
            return JsonResponse({'status': 'erro', 'erro': 'E-mail inválido.'})

        try:
            NewsletterInscricao.objects.create(email=email)
        except IntegrityError:
            # e-mail já inscrito — retorna ok silencioso (não revela existência)
            return JsonResponse({'status': 'ok'})

        return JsonResponse({'status': 'ok'})

    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'status': 'erro', 'erro': 'Requisição inválida.'}, status=400)
    except Exception:
        return JsonResponse({'status': 'erro', 'erro': 'Tente novamente.'}, status=500)
