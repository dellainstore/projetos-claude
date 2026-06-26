def newsletter_status(request):
    """Indica se o usuário logado já está inscrito na newsletter e expõe a
    oferta de cupom de boas-vindas (se houver template ativo).

    NewsletterInscricao é a fonte da verdade — o flag recebe_newsletter no User
    é apenas um cache denormalizado e é sincronizado quando estiver fora de sync
    (ex: admin excluiu a inscrição mas o flag continua True).
    """
    from django.core.cache import cache
    from apps.core_utils.cache_utils import NEWSLETTER_OFERTA

    inscrito = False
    if request.user.is_authenticated:
        from apps.produtos.models import NewsletterInscricao
        inscrito = NewsletterInscricao.objects.filter(
            email__iexact=request.user.email, ativo=True
        ).exists()
        if inscrito != bool(request.user.recebe_newsletter):
            request.user.__class__.objects.filter(pk=request.user.pk).update(
                recebe_newsletter=inscrito
            )

    oferta = cache.get(NEWSLETTER_OFERTA)
    if oferta is None:
        try:
            from apps.pedidos.models import Cupom
            c = (Cupom.objects
                 .filter(origem='newsletter', ativo=True, dias_validade_pos_emissao__isnull=False)
                 .order_by('-id')
                 .first())
            if c:
                if c.tipo == 'percentual':
                    valor_int = int(c.valor) if c.valor == int(c.valor) else c.valor
                    valor_label = f'{valor_int}% de desconto'
                else:
                    v = f'{c.valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
                    valor_label = f'R$ {v} de desconto'
                oferta = {'valor_label': valor_label, 'dias': int(c.dias_validade_pos_emissao)}
            else:
                oferta = {}
        except Exception:
            oferta = {}
        cache.set(NEWSLETTER_OFERTA, oferta, 60 * 60)  # 1h

    return {
        'usuario_inscrito_newsletter': inscrito,
        'cupom_newsletter_oferta':     oferta or None,
    }


def tracking_flash(request):
    """
    Le e consome flags de tracking de sessao (login, signup) para disparo
    client-side de eventos GA4 e Meta Pixel na proxima pagina carregada apos
    a acao. Limpa os flags para que nao disparem novamente em revisitas.
    """
    track_login = False
    track_signup_event_id = ''

    if hasattr(request, 'session'):
        if request.session.get('_track_login'):
            track_login = True
            try:
                del request.session['_track_login']
                request.session.modified = True
            except KeyError:
                pass

        signup_event_id = request.session.get('_track_signup_event_id', '')
        if signup_event_id:
            track_signup_event_id = signup_event_id
            try:
                del request.session['_track_signup_event_id']
                request.session.modified = True
            except KeyError:
                pass

    return {
        'track_login': track_login,
        'track_signup_event_id': track_signup_event_id,
    }


def categorias_menu(request):
    """
    Injeta categorias ativas, números de WhatsApp e frases da tarja em todos os templates.
    Cache de 4 horas (categorias) e 1 hora (tarja) — invalidados automaticamente no admin.
    """
    from django.core.cache import cache
    from django.conf import settings
    from apps.core_utils.cache_utils import MENU_CATEGORIAS, TARJA_FRASES, LOJA_CONFIG
    from apps.produtos.models import Categoria

    categorias = cache.get(MENU_CATEGORIAS)
    if categorias is None:
        try:
            categorias = list(
                Categoria.objects
                .filter(ativa=True, parent__isnull=True)
                .prefetch_related('subcategorias')
                .order_by('ordem', 'nome')
            )
        except Exception:
            categorias = []
        cache.set(MENU_CATEGORIAS, categorias, 60 * 60 * 4)

    tarja_frases = cache.get(TARJA_FRASES)
    if tarja_frases is None:
        try:
            from apps.conteudo.models import TarjaFrase
            tarja_frases = list(
                TarjaFrase.objects.filter(ativa=True).order_by('ordem', 'id')[:6]
            )
        except Exception:
            tarja_frases = []
        cache.set(TARJA_FRASES, tarja_frases, 60 * 60)

    config_loja = cache.get(LOJA_CONFIG)
    if config_loja is None:
        try:
            from apps.conteudo.models import ConfiguracaoLoja
            config_loja = ConfiguracaoLoja.get_config()
        except Exception:
            config_loja = None
        cache.set(LOJA_CONFIG, config_loja, 60 * 60 * 24)
    frete_meta = getattr(config_loja, 'frete_gratis_acima', None) if config_loja else None

    meta_am = {}
    if getattr(settings, 'META_PIXEL_ID', '') and request.user.is_authenticated:
        from apps.core_utils.meta import _sha256, _normalize_phone, _digits_only
        email_raw = (getattr(request.user, 'email', '') or '').strip().lower()
        phone_raw = getattr(request.user, 'telefone', '') or ''
        cpf_raw   = getattr(request.user, 'cpf', '') or ''
        em  = _sha256(email_raw)
        ph  = _sha256(_normalize_phone(phone_raw))
        ext = _sha256(_digits_only(cpf_raw)) or _sha256(str(request.user.pk))
        if em:
            meta_am['em'] = em
        if ph:
            meta_am['ph'] = ph
        if ext:
            meta_am['external_id'] = ext

    return {
        'categorias_menu':  categorias,
        'tarja_frases':     tarja_frases,
        'frete_meta':       frete_meta,
        'WHATSAPP_NUMBER_1': getattr(settings, 'WHATSAPP_NUMBER_1', ''),
        'WHATSAPP_NUMBER_2': getattr(settings, 'WHATSAPP_NUMBER_2', ''),
        'META_PIXEL_ID':       getattr(settings, 'META_PIXEL_ID', ''),
        'GA_MEASUREMENT_ID':   getattr(settings, 'GA_MEASUREMENT_ID', ''),
        'CLARITY_PROJECT_ID':  getattr(settings, 'CLARITY_PROJECT_ID', ''),
        'meta_am':             meta_am,
    }
