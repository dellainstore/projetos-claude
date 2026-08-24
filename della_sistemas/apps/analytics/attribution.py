"""Classificacao de origem de trafego, em linguagem de gente.

Fonte unica usada pelo dashboard ao vivo (`_calcular_origens`), pelo relatorio
semanal em PDF (`gerar_relatorio_semanal`) e pelos paineis de Visitas e Vendas.
Manter uma unica implementacao evita que divirjam (ja aconteceu ate 2026-07-08:
sessao com fbclid e sem utm_source aparecia como "Meta" no dashboard e
"Direto / Outros" no relatorio semanal).

Os rotulos sao escritos para quem nunca ouviu falar de UTM. As siglas cruas que
a Meta grava (`ig`, `fb`, `th`, `IGShopping`) nunca chegam a tela.
"""

from urllib.parse import unquote_plus

# Rotulos. Centralizados aqui para o painel, o PDF e os filtros usarem o mesmo
# texto, sem string solta espalhada pelos templates.
ANUNCIO_INSTAGRAM = 'Anúncio no Instagram'
ANUNCIO_FACEBOOK  = 'Anúncio no Facebook'
ANUNCIO_THREADS   = 'Anúncio no Threads'
ANUNCIO_META      = 'Anúncio da Meta'
LOJA_INSTAGRAM    = 'Loja do Instagram'
LINK_BIO          = 'Link da bio'
STORY_INSTAGRAM   = 'Story do Instagram'
POST_INSTAGRAM    = 'Post do Instagram'
REELS_INSTAGRAM   = 'Reels do Instagram'
POST_FACEBOOK     = 'Post do Facebook'
INSTAGRAM_PERFIL  = 'Instagram (perfil)'
FACEBOOK_PERFIL   = 'Facebook (perfil)'
WHATSAPP          = 'WhatsApp'
GOOGLE            = 'Google'
EMAIL             = 'E-mail'
DIRETO            = 'Direto ou busca'

# Origens que representam midia paga. Usado pelo painel de Anuncios e pelo card
# "quanto do faturamento veio de anuncio".
ORIGENS_PAGAS = frozenset((
    ANUNCIO_INSTAGRAM, ANUNCIO_FACEBOOK, ANUNCIO_THREADS, ANUNCIO_META,
))


def label_origem(source: str, tem_fbclid: bool = False, tem_gclid: bool = False,
                 medium: str = '') -> str:
    """Nome legivel da origem de uma sessao ou de um pedido.

    `medium` separa o que a mesma origem faz de graca do que ela faz pago: a
    Meta grava `utm_source=ig` tanto no anuncio quanto no link do perfil, e so
    o `utm_medium=paid` distingue os dois. Sem ele, verba de anuncio aparecia
    somada ao alcance organico do Instagram.
    """
    s = (source or '').lower().strip()
    m = (medium or '').lower().strip()
    pago = m in ('paid', 'cpc', 'ppc', 'paid_social')

    # Instagram, nas suas quatro formas distintas.
    if s == 'igshopping':
        return LOJA_INSTAGRAM
    if s in ('ig', 'instagram') or 'instagram' in s:
        if pago:
            return ANUNCIO_INSTAGRAM
        if m == 'bio':
            return LINK_BIO
        # Postagens organicas etiquetadas a mao (ver o gerador de links em
        # Site > Gerar link). Separar story de post e de reels responde qual
        # formato faz a cliente sair do Instagram e vir comprar.
        if m in ('story', 'stories'):
            return STORY_INSTAGRAM
        if m in ('post', 'feed'):
            return POST_INSTAGRAM
        if m in ('reels', 'reel'):
            return REELS_INSTAGRAM
        return INSTAGRAM_PERFIL

    if s in ('fb', 'facebook') or 'facebook' in s:
        if pago:
            return ANUNCIO_FACEBOOK
        if m in ('post', 'feed'):
            return POST_FACEBOOK
        return FACEBOOK_PERFIL

    # "th" e o Threads: a Meta preenche a origem sozinha com a sigla da rede
    # onde o anuncio foi entregue (ig, fb, th, msg) via {{site_source_name}}.
    if s == 'th' or 'threads' in s:
        return ANUNCIO_THREADS

    if s in ('msg', 'messenger'):
        return ANUNCIO_META if pago else 'Messenger'
    if 'meta' in s:
        return ANUNCIO_META if pago else 'Meta'
    if 'google' in s:
        return GOOGLE
    if 'whatsapp' in s or 'wapp' in s:
        return WHATSAPP
    if s in ('email', 'e-mail', 'newsletter', 'brevo'):
        return EMAIL

    if s:
        return s.capitalize()

    # Sem origem marcada. O clique de anuncio ainda revela a midia paga: o
    # fbclid/gclid so existe quando a pessoa CLICOU num anuncio. Sem este
    # fallback, verba paga aparece como "direto" (eram 176 visitas e 2 vendas
    # em 30 dias, medido em 2026-08-23).
    if tem_fbclid:
        return ANUNCIO_META
    if tem_gclid:
        return GOOGLE
    # Etiqueta pela metade: a Meta mandou o medium mas nao a origem. Continua
    # sendo anuncio, e nao pode cair no balde de "direto".
    if pago:
        return ANUNCIO_META
    return DIRETO


def nome_campanha(valor: str) -> str:
    """Nome de campanha legivel.

    Parte das campanhas chega com o nome codificado como viaja na URL
    (`CAMPANHA+%7C+BODY+POST%7C+100R%24+...`), porque a Meta aplica o
    percent-encoding antes de substituir a macro `{{campaign.name}}`. Sem
    decodificar, a MESMA campanha aparece como duas linhas diferentes na
    tabela, uma delas ilegivel.
    """
    if not valor:
        return ''
    try:
        # `unquote_plus` tambem troca "+" por espaco, que e como a Meta escreve
        # o espaco nesses casos.
        limpo = unquote_plus(valor).strip()
    except Exception:
        limpo = valor

    # Campanha etiquetada com {{campaign.id}} em vez de {{campaign.name}}: o
    # valor e so o codigo numerico da Meta, ilegivel na tela. Enquanto as
    # campanhas nao forem repadronizadas para mandar codigo E nome, mostra os
    # ultimos digitos, que ja bastam para distinguir uma campanha da outra sem
    # ocupar a coluna inteira.
    if limpo.isdigit() and len(limpo) > 8:
        return f'Campanha {limpo[-6:]}'
    return limpo
