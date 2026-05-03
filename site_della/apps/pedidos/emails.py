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

logger = logging.getLogger(__name__)

SITE_URL = getattr(settings, 'SITE_URL', 'https://www.dellainstore.com.br')


def enviar_confirmacao_pedido(pedido) -> bool:
    """
    Envia e-mail de confirmação de pedido ao cliente.
    Retorna True em caso de sucesso, False se falhar.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL}
        html = render_to_string('emails/confirmacao_pedido.html', ctx)
        texto = _texto_confirmacao(pedido)

        msg = EmailMultiAlternatives(
            subject  = f'Pedido {pedido.numero} recebido — Della Instore',
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
        ctx = {'pedido': pedido, 'site_url': SITE_URL}
        html = render_to_string('emails/envio_rastreio.html', ctx)
        texto = _texto_envio(pedido)

        msg = EmailMultiAlternatives(
            subject  = f'Seu pedido {pedido.numero} foi enviado! — Della Instore',
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
    Envia e-mail ao cliente informando que o pagamento foi confirmado e o pedido está em separação.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL}
        html = render_to_string('emails/pagamento_confirmado.html', ctx)
        texto = _texto_pagamento_confirmado(pedido)

        msg = EmailMultiAlternatives(
            subject    = f'Pagamento confirmado — Pedido {pedido.numero} em separação',
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


def enviar_cancelamento(pedido, estornado: bool = False) -> bool:
    """
    Envia e-mail ao cliente informando o cancelamento do pedido.
    Se estornado=True, menciona o estorno automático no e-mail.
    """
    try:
        ctx = {'pedido': pedido, 'site_url': SITE_URL, 'estornado': estornado}
        html = render_to_string('emails/cancelamento_pedido.html', ctx)
        texto = _texto_cancelamento(pedido, estornado)

        msg = EmailMultiAlternatives(
            subject    = f'Pedido {pedido.numero} cancelado — Della Instore',
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
        logo_url  = SITE_URL + static('images/brand/logo-della-white.png')
        itens_fmt = [
            {**item, 'subtotal': _brl(item.get('subtotal', 0))}
            for item in ca.itens
        ]
        ctx = {
            'ca': ca,
            'itens': itens_fmt,
            'total_fmt': _brl(ca.total),
            'site_url': SITE_URL,
            'whatsapp_number': whatsapp,
            'logo_url': logo_url,
        }
        html = render_to_string('emails/carrinho_abandonado.html', ctx)
        texto = _texto_carrinho_abandonado(ca)

        nome_curto = (ca.nome or '').split()[0] if ca.nome else 'cliente'
        msg = EmailMultiAlternatives(
            subject    = f"D'ELLA Instore — {nome_curto}, sua seleção ainda está disponível",
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
    for item in pedido.itens.all():
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
    linhas = [
        f'Olá, {nome}!',
        '',
        f'Seu pagamento foi confirmado! O pedido {pedido.numero} já está em separação.',
        '',
        'ITENS:',
    ]
    for item in pedido.itens.all():
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
        'Della Instore — Moda Feminina Premium',
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
        f'Finalizar compra: {SITE_URL}/carrinho/',
        '',
        'Qualquer dúvida, entre em contato: contato@dellainstore.com.br',
        '',
        'Della Instore — Moda Feminina Premium',
    ]
    return '\n'.join(linhas)
