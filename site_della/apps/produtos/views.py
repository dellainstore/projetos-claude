from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Count
from django.conf import settings


def homepage(request):
    from apps.produtos.models import Categoria, Produto, Avaliacao

    try:
        categorias_destaque = Categoria.objects.filter(ativa=True).order_by('ordem')[:8]
        produtos_destaque   = Produto.objects.filter(ativo=True, destaque=True).prefetch_related('imagens')[:8]
        depoimentos         = Avaliacao.objects.filter(aprovada=True).order_by('-criada_em')[:3]
        look_produtos       = Produto.objects.filter(ativo=True).prefetch_related('imagens')[:3]
    except Exception:
        categorias_destaque = []
        produtos_destaque   = []
        depoimentos         = []
        look_produtos       = []

    wishlist_ids = set()
    if request.user.is_authenticated:
        try:
            wishlist_ids = set(request.user.wishlist_set.values_list('produto_id', flat=True))
        except Exception:
            pass

    context = {
        'categorias_destaque':    categorias_destaque,
        'categorias_placeholder': ['Body', 'Underwear', 'Beachwear', 'Casual'],
        'produtos_destaque':      produtos_destaque,
        'depoimentos':            depoimentos,
        'look_produtos':          look_produtos,
        'wishlist_ids':           wishlist_ids,
        'instagram_posts':        [],
        'WHATSAPP_NUMBER_1':      settings.WHATSAPP_NUMBER_1,
        'WHATSAPP_NUMBER_2':      settings.WHATSAPP_NUMBER_2,
    }
    return render(request, 'home/index.html', context)


def loja(request, categoria_slug=None):
    from apps.produtos.models import Categoria, Produto

    categorias = Categoria.objects.filter(ativa=True).order_by('ordem')
    categoria_ativa = None

    produtos_qs = Produto.objects.filter(ativo=True).prefetch_related('imagens', 'variacoes')

    if categoria_slug:
        categoria_ativa = get_object_or_404(Categoria, slug=categoria_slug, ativa=True)
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

    imagens      = produto.imagens.order_by('-principal', 'ordem')
    variacoes_tamanho = produto.variacoes.filter(tipo='tamanho', ativa=True)
    variacoes_cor     = produto.variacoes.filter(tipo='cor', ativa=True)
    avaliacoes   = produto.avaliacoes.filter(aprovada=True).order_by('-criada_em')[:10]

    media_notas  = avaliacoes.aggregate(media=Avg('nota'))['media'] or 0
    total_aval   = produto.avaliacoes.filter(aprovada=True).count()

    # Produtos relacionados (mesma categoria, exceto o atual)
    relacionados = (
        Produto.objects
        .filter(ativo=True, categoria=produto.categoria)
        .exclude(pk=produto.pk)
        .prefetch_related('imagens')
        .order_by('-destaque', '-criado_em')[:4]
    )

    na_wishlist = False
    if request.user.is_authenticated:
        try:
            na_wishlist = request.user.wishlist_set.filter(produto=produto).exists()
        except Exception:
            pass

    context = {
        'produto':            produto,
        'imagens':            imagens,
        'variacoes_tamanho':  variacoes_tamanho,
        'variacoes_cor':      variacoes_cor,
        'avaliacoes':         avaliacoes,
        'media_notas':        round(media_notas, 1),
        'total_aval':         total_aval,
        'relacionados':       relacionados,
        'na_wishlist':        na_wishlist,
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


def sobre(request):
    return render(request, 'home/sobre.html')


def contato(request):
    return render(request, 'home/contato.html')


def politica_privacidade(request):
    return render(request, 'home/politica_privacidade.html')


def trocas_devolucoes(request):
    return render(request, 'home/trocas_devolucoes.html')


@require_POST
def newsletter_signup(request):
    import json
    from apps.core_utils.sanitize import sanitize_text

    try:
        data  = json.loads(request.body)
        email = sanitize_text(data.get('email', ''), max_length=254).lower()

        if not email or '@' not in email or '.' not in email:
            return JsonResponse({'status': 'erro', 'erro': 'E-mail inválido.'})

        # TODO: salvar no banco e enviar e-mail de confirmação
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'erro', 'erro': 'Tente novamente.'}, status=400)
