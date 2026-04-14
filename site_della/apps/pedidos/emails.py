"""
E-mails transacionais relacionados a pedidos.

Funções:
    enviar_confirmacao_pedido(pedido)   — chamada ao criar o pedido no checkout
    enviar_notificacao_envio(pedido)    — chamada ao marcar status como "enviado"
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
