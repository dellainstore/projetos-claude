"""
E-mails transacionais relacionados a pedidos.

Funções:
    enviar_confirmacao_pedido(pedido)         — chamada ao criar o pedido no checkout
    enviar_notificacao_envio(pedido)          — chamada ao marcar status como "enviado"
    enviar_email_carrinho_abandonado(ca)      — lembrete de carrinho não finalizado
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

logger = logging.getLogger(__name__)

SITE_URL = getattr(settings, 'SITE_URL', 'https://www.dellainstore.com.br')


def _ctx_base() -> dict:
    from django.templatetags.static import static
    return {
        'whatsapp_number': getattr(settings, 'WHATSAPP_NUMBER_1', '5511988879928'),
        'logo_url': SITE_URL + static('images/brand/logo-della.png'),
    }


def enviar_confirmacao_pedido(pedido) -> bool:
    """
    Envia e-mail de confirmação de pedido ao cliente.
    Retorna True em caso de sucesso, False se falhar.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, **_ctx_base()}
        html = render_to_string('emails/confirmacao_pedido.html', ctx)
        texto = _texto_confirmacao(pedido)

        msg = EmailMultiAlternatives(
            subject  = f'Pedido {pedido.numero} recebido na Della Instore',
            body     = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to       = [pedido.email],
            bcc      = ['financeiro@dellainstore.com.br'],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de confirmação enviado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de confirmação do pedido %s: %s', pedido.numero, exc)
        return False


def enviar_notificacao_envio(pedido) -> bool:
    """
    Envia e-mail de notificação de envio com código de rastreio.
    Retorna True em caso de sucesso, False se falhar.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, **_ctx_base()}
        html = render_to_string('emails/envio_rastreio.html', ctx)
        texto = _texto_envio(pedido)

        msg = EmailMultiAlternatives(
            subject  = f'Seu pedido {pedido.numero} foi enviado pela Della Instore',
            body     = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to       = [pedido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de envio disparado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de envio do pedido %s: %s', pedido.numero, exc)
        return False


def _brl(valor):
    """Formata número/string para padrão brasileiro: 1.234,56"""
    try:
        v = float(str(valor).replace(',', '.'))
        return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return str(valor)


def enviar_confirmacao_pagamento(pedido) -> bool:
    """
    Envia e-mail ao cliente informando que o pagamento foi confirmado.
    Para retirada na loja: template diferente, sem mencionar envio.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, **_ctx_base()}
        if pedido.retirada_loja:
            html = render_to_string('emails/pagamento_confirmado_retirada.html', ctx)
            texto = _texto_pagamento_confirmado(pedido)
            subject = f'Pagamento confirmado pedido {pedido.numero} - prepare-se para retirar!'
        else:
            html = render_to_string('emails/pagamento_confirmado.html', ctx)
            texto = _texto_pagamento_confirmado(pedido)
            subject = f'Pagamento confirmado pedido {pedido.numero} em separação'

        msg = EmailMultiAlternatives(
            subject    = subject,
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [pedido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de pagamento confirmado enviado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de pagamento confirmado do pedido %s: %s', pedido.numero, exc)
        return False


def enviar_pronto_retirada(pedido) -> bool:
    """
    Envia e-mail ao cliente informando que o pedido esta pronto para retirada na loja.
    Chamado ao marcar status pronto_retirada no admin.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, **_ctx_base()}
        html = render_to_string('emails/pronto_retirada.html', ctx)
        texto = _texto_pronto_retirada(pedido)

        msg = EmailMultiAlternatives(
            subject    = f'Seu pedido {pedido.numero} esta pronto para retirada na D\'ELLA Instore!',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [pedido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de pronto para retirada enviado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de pronto para retirada do pedido %s: %s', pedido.numero, exc)
        return False


def enviar_cancelamento(pedido, estornado: bool = False) -> bool:
    """
    Envia e-mail ao cliente informando o cancelamento do pedido.
    Se estornado=True, menciona o estorno automático no e-mail.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, 'estornado': estornado, **_ctx_base()}
        html = render_to_string('emails/cancelamento_pedido.html', ctx)
        texto = _texto_cancelamento(pedido, estornado)

        msg = EmailMultiAlternatives(
            subject    = f'Pedido {pedido.numero} cancelado na Della Instore',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [pedido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de cancelamento enviado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de cancelamento do pedido %s: %s', pedido.numero, exc)
        return False


def enviar_confirmacao_entrega(pedido) -> bool:
    """
    Envia e-mail ao cliente confirmando a entrega e convidando-o a avaliar a loja.
    """
    if pedido.avaliacao_email_enviado_em:
        logger.info('E-mail de avaliação já enviado anteriormente para o pedido %s', pedido.numero)
        return True

    try:
        link_avaliacao = f'{SITE_URL}/avaliacoes/pedido/{pedido.numero}/'
        ctx = {'pedido': pedido, 'site_url': SITE_URL, 'link_avaliacao': link_avaliacao, **_ctx_base()}
        html = render_to_string('emails/entregue_avaliacao.html', ctx)
        texto = _texto_entregue(pedido)

        msg = EmailMultiAlternatives(
            subject    = f'Seu pedido {pedido.numero} foi entregue! Conte o que achou 💛',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [pedido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()
        pedido.avaliacao_email_enviado_em = timezone.now()
        pedido.save(update_fields=['avaliacao_email_enviado_em'])

        logger.info('E-mail de entrega+avaliação enviado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de entrega do pedido %s: %s', pedido.numero, exc)
        return False


def enviar_saiu_para_entrega(pedido) -> bool:
    """
    Envia e-mail ao cliente informando que o pedido saiu para entrega.
    Chamado automaticamente pelo cron de rastreio Correios.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, **_ctx_base()}
        html = render_to_string('emails/saiu_para_entrega.html', ctx)
        texto = _texto_saiu_para_entrega(pedido)

        msg = EmailMultiAlternatives(
            subject    = f'Seu pedido {pedido.numero} está a caminho com a Della Instore',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [pedido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail "saiu para entrega" enviado para %s (pedido %s)', pedido.email, pedido.numero)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail "saiu para entrega" do pedido %s: %s', pedido.numero, exc)
        return False


def enviar_email_carrinho_abandonado(ca) -> bool:
    """
    Envia lembrete de carrinho abandonado ao cliente.
    `ca` é uma instância de CarrinhoAbandonado.
    Retorna True em caso de sucesso, False se falhar.
    """
    from django.utils import timezone

    try:
        from django.templatetags.static import static
        whatsapp  = getattr(settings, 'WHATSAPP_NUMBER_1', '5511988879928')
        logo_url  = SITE_URL + static('images/brand/logo-della.png')
        def _abs_url(url):
            if url and not url.startswith('http'):
                return SITE_URL + url
            return url

        itens_fmt = [
            {**item, 'subtotal': _brl(item.get('subtotal', 0)), 'imagem': _abs_url(item.get('imagem', ''))}
            for item in ca.itens
        ]
        link_recuperar = f'{SITE_URL}/carrinho/recuperar/{ca.token}/'
        ctx = {
            'ca': ca,
            'itens': itens_fmt,
            'total_fmt': _brl(ca.total),
            'site_url': SITE_URL,
            'link_recuperar': link_recuperar,
            'whatsapp_number': whatsapp,
            'logo_url': logo_url,
        }
        html = render_to_string('emails/carrinho_abandonado.html', ctx)
        texto = _texto_carrinho_abandonado(ca)

        nome_curto = (ca.nome or '').split()[0] if ca.nome else 'cliente'
        msg = EmailMultiAlternatives(
            subject    = f"{nome_curto} sua seleção Della Instore ainda está disponível",
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [ca.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        ca.email_enviado    = True
        ca.email_enviado_em = timezone.now()
        ca.save(update_fields=['email_enviado', 'email_enviado_em'])

        logger.info('E-mail de carrinho abandonado enviado para %s', ca.email)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de carrinho abandonado para %s: %s', ca.email, exc)
        return False


def enviar_email_cupom_newsletter(cupom_emitido) -> bool:
    """
    Envia e-mail com o código de cupom gerado a partir da inscrição na newsletter.
    `cupom_emitido` é uma instância de CupomEmitido.
    Retorna True em caso de sucesso, False se falhar.
    """
    try:
        from django.templatetags.static import static
        whatsapp = getattr(settings, 'WHATSAPP_NUMBER_1', '5511988879928')
        logo_url = SITE_URL + static('images/brand/logo-della.png')

        template = cupom_emitido.cupom_template
        if template.tipo == 'percentual':
            valor_fmt = f'{int(template.valor) if template.valor == int(template.valor) else template.valor}%'
        else:
            valor_fmt = f'R$ {_brl(template.valor)}'

        ctx = {
            'cupom': cupom_emitido,
            'template': template,
            'valor_fmt': valor_fmt,
            'dias_validade': template.dias_validade_pos_emissao,
            'expira_em': cupom_emitido.expira_em,
            'site_url': SITE_URL,
            'whatsapp_number': whatsapp,
            'logo_url': logo_url,
        }
        html = render_to_string('emails/cupom_newsletter.html', ctx)
        texto = (
            f'Obrigada por se inscrever na newsletter Della Instore!\n\n'
            f'Seu cupom de {valor_fmt} de desconto: {cupom_emitido.codigo}\n'
            f'Válido por {template.dias_validade_pos_emissao} dias a partir de hoje.\n\n'
            f'Use no checkout da sua próxima compra em {SITE_URL}.\n'
        )

        msg = EmailMultiAlternatives(
            subject    = f'Seu cupom de {valor_fmt} de desconto Della Instore',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [cupom_emitido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de cupom newsletter enviado para %s (código %s)', cupom_emitido.email, cupom_emitido.codigo)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de cupom newsletter para %s: %s', cupom_emitido.email, exc)
        return False


def enviar_email_cupom_aniversario(cupom_emitido) -> bool:
    """
    Envia e-mail com o código de cupom de aniversário ao cliente.
    `cupom_emitido` é uma instância de CupomEmitido (com cliente preenchido).
    Retorna True em caso de sucesso, False se falhar.
    """
    try:
        from django.templatetags.static import static
        whatsapp = getattr(settings, 'WHATSAPP_NUMBER_1', '5511988879928')
        logo_url = SITE_URL + static('images/brand/logo-della.png')

        template = cupom_emitido.cupom_template
        if template.tipo == 'percentual':
            valor_fmt = f'{int(template.valor) if template.valor == int(template.valor) else template.valor}%'
        else:
            valor_fmt = f'R$ {_brl(template.valor)}'

        nome_curto = ''
        if cupom_emitido.cliente and cupom_emitido.cliente.nome:
            nome_curto = cupom_emitido.cliente.nome.split()[0]

        ctx = {
            'cupom': cupom_emitido,
            'template': template,
            'valor_fmt': valor_fmt,
            'dias_validade': template.dias_validade_pos_emissao,
            'expira_em': cupom_emitido.expira_em,
            'nome': nome_curto,
            'site_url': SITE_URL,
            'whatsapp_number': whatsapp,
            'logo_url': logo_url,
        }
        html = render_to_string('emails/cupom_aniversario.html', ctx)
        saudacao = f'Olá, {nome_curto}!\n\n' if nome_curto else 'Olá!\n\n'
        texto = (
            f'{saudacao}'
            f'Hoje é o seu dia! O time D\'ELLA preparou um presente especial: '
            f'{valor_fmt} de desconto na sua próxima compra.\n\n'
            f'Seu cupom: {cupom_emitido.codigo}\n'
            f'Válido por {template.dias_validade_pos_emissao} dias.\n\n'
            f'Use no checkout em {SITE_URL}.\n'
        )

        msg = EmailMultiAlternatives(
            subject    = f'Feliz aniversário! Seu presente de {valor_fmt} D\'ELLA Instore',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [cupom_emitido.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de cupom aniversário enviado para %s (código %s)', cupom_emitido.email, cupom_emitido.codigo)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de cupom aniversário para %s: %s', cupom_emitido.email, exc)
        return False


# ── Versões texto plano ───────────────────────────────────────────────────────

def _texto_confirmacao(pedido) -> str:
    linhas = [
        f'Olá, {pedido.nome_completo.split()[0]}!',
        '',
        f'Seu pedido foi recebido com sucesso.',
        f'',
        f'NÚMERO DO PEDIDO: {pedido.numero}',
        f'Data: {pedido.criado_em.strftime("%d/%m/%Y %H:%M")}',
        '',
        'ITENS:',
    ]
    for item in pedido.itens.select_related('produto', 'variacao').all():
        desc = f'  {item.quantidade}x {item.nome_produto}'
        if item.variacao_desc:
            desc += f' — {item.variacao_desc}'
        desc += f'  R$ {item.subtotal:.2f}'
        linhas.append(desc)

    linhas += [
        '',
        f'Subtotal: R$ {pedido.subtotal:.2f}',
        f'Frete:    R$ {pedido.frete:.2f}',
        f'TOTAL:    R$ {pedido.total:.2f}',
        '',
        'ENDEREÇO DE ENTREGA:',
        f'  {pedido.logradouro}, {pedido.numero_entrega}',
        f'  {pedido.bairro} — {pedido.cidade}/{pedido.estado}',
        f'  CEP: {pedido.cep_entrega[:5]}-{pedido.cep_entrega[5:]}',
        '',
        f'Acompanhe seu pedido em: {SITE_URL}/conta/minha-conta/pedidos/{pedido.numero}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)


def _texto_envio(pedido) -> str:
    linhas = [
        f'Olá, {pedido.nome_completo.split()[0]}!',
        '',
        f'Seu pedido {pedido.numero} foi enviado e já está a caminho!',
        '',
    ]
    if pedido.codigo_rastreio:
        linhas += [
            f'CÓDIGO DE RASTREIO: {pedido.codigo_rastreio}',
        ]
        if pedido.transportadora:
            linhas.append(f'Transportadora: {pedido.transportadora}')
        linhas += [
            '',
            'Rastreie em: https://www.correios.com.br/rastreamento',
            '',
        ]
    linhas += [
        f'Acompanhe seu pedido em: {SITE_URL}/conta/minha-conta/pedidos/{pedido.numero}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)


def _texto_pagamento_confirmado(pedido) -> str:
    nome = pedido.nome_completo.split()[0]
    if pedido.retirada_loja:
        linhas = [
            f'Olá, {nome}!',
            '',
            f'Seu pagamento foi confirmado! Estamos preparando seu pedido {pedido.numero} para retirada.',
            'Avisaremos quando estiver pronto para você buscar na loja.',
            '',
            'ITENS:',
        ]
    else:
        linhas = [
            f'Olá, {nome}!',
            '',
            f'Seu pagamento foi confirmado! O pedido {pedido.numero} já está em separação.',
            '',
            'ITENS:',
        ]
    for item in pedido.itens.select_related('produto', 'variacao').all():
        desc = f'  {item.quantidade}x {item.nome_produto}'
        if item.variacao_desc:
            desc += f' — {item.variacao_desc}'
        linhas.append(desc)
    linhas += [
        '',
        f'Total: R$ {pedido.total:.2f}',
        '',
        f'Acompanhe seu pedido em: {SITE_URL}/conta/minha-conta/pedidos/{pedido.numero}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        "Della Instore - Moda Feminina Premium",
    ]
    return '\n'.join(linhas)


def _texto_pronto_retirada(pedido) -> str:
    nome = pedido.nome_completo.split()[0]
    linhas = [
        f'Olá, {nome}!',
        '',
        f'Seu pedido {pedido.numero} está pronto para retirada na D\'ELLA Instore!',
        '',
        'HORÁRIOS DE FUNCIONAMENTO:',
        '  Segunda a Quinta: 10h às 19h',
        '  Sexta: 10h às 18h',
        '  Sábado: horário a confirmar pelo WhatsApp',
        '',
        'ENDEREÇO:',
        '  Rua Visconde da Luz, 183 - Vila Nova Conceicao, Sao Paulo/SP',
        '',
        f'Acompanhe seu pedido em: {SITE_URL}/conta/minha-conta/pedidos/{pedido.numero}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        "Della Instore - Moda Feminina Premium",
    ]
    return '\n'.join(linhas)


def _texto_cancelamento(pedido, estornado: bool) -> str:
    nome = pedido.nome_completo.split()[0]
    linhas = [
        f'Olá, {nome}!',
        '',
        f'Seu pedido {pedido.numero} foi cancelado.',
        '',
    ]
    if estornado:
        linhas += [
            f'O valor de R$ {pedido.total:.2f} será estornado automaticamente '
            'ao meio de pagamento utilizado em até 5 dias úteis.',
            '',
        ]
    else:
        linhas += [
            'Caso você já tenha realizado o pagamento e não tenha recebido informações '
            'sobre o estorno, entre em contato conosco.',
            '',
        ]
    linhas += [
        f'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)


def _texto_entregue(pedido) -> str:
    nome = pedido.nome_completo.split()[0]
    link_avaliacao = f'{SITE_URL}/avaliacoes/pedido/{pedido.numero}/'
    linhas = [
        f'Olá, {nome}!',
        '',
        f'Seu pedido {pedido.numero} foi entregue! Esperamos que você adore.',
        '',
        'Que tal nos contar o que achou? Sua avaliação ajuda outras clientes a',
        'conhecer melhor a D\'ELLA Instore.',
        '',
        f'Avaliar na loja: {link_avaliacao}',
        '',
        f'Acompanhe seu pedido em: {SITE_URL}/conta/minha-conta/pedidos/{pedido.numero}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)


def _texto_saiu_para_entrega(pedido) -> str:
    nome = pedido.nome_completo.split()[0]
    linhas = [
        f'Olá, {nome}!',
        '',
        f'Seu pedido {pedido.numero} saiu para entrega hoje!',
        'Fique de olho — em breve o seu item chegará até você.',
        '',
    ]
    if pedido.codigo_rastreio:
        linhas += [
            f'Código de rastreio: {pedido.codigo_rastreio}',
            f'Rastreie em: https://www.linkcorreios.com.br/?id={pedido.codigo_rastreio}',
            '',
        ]
    linhas += [
        f'Acompanhe seu pedido em: {SITE_URL}/conta/minha-conta/pedidos/{pedido.numero}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)


def _texto_carrinho_abandonado(ca) -> str:
    nome_curto = (ca.nome or '').split()[0] if ca.nome else 'cliente'
    linhas = [
        f'Olá, {nome_curto}!',
        '',
        'Sua seleção ainda está disponível.',
        'Você selecionou peças exclusivas da D\'ELLA que foram produzidas em quantidade limitada e elas ainda estão reservadas para você. Finalize agora e aproveite!',
        '',
        'ITENS NO SEU CARRINHO:',
    ]
    for item in ca.itens:
        desc = f'  {item.get("quantidade", 1)}x {item.get("nome", "")}'
        if item.get('variacao_desc'):
            desc += f' — {item["variacao_desc"]}'
        desc += f'  R$ {item.get("subtotal", "")}'
        linhas.append(desc)

    linhas += [
        '',
        f'Total: R$ {ca.total}',
        '',
        f'Finalizar compra: {SITE_URL}/carrinho/recuperar/{ca.token}/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)
