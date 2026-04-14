"""
E-mails transacionais relacionados a usuários.

Funções:
    enviar_recuperacao_senha(usuario, link) — recuperação de senha com link seguro
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def enviar_recuperacao_senha(usuario, link: str) -> bool:
    """
    Envia e-mail HTML de recuperação de senha.
    Retorna True em caso de sucesso, False se falhar.
    """
    try:
        ctx = {'usuario': usuario, 'link': link}
        html = render_to_string('emails/recuperacao_senha.html', ctx)
        texto = (
            f'Olá, {usuario.nome}!\n\n'
            f'Recebemos uma solicitação para redefinir a senha da sua conta Della Instore.\n\n'
            f'Acesse o link abaixo para criar uma nova senha (válido por 24 horas):\n'
            f'{link}\n\n'
            f'Se você não solicitou a redefinição, ignore este e-mail.\n\n'
            f'Della Instore — Moda Feminina Premium\n'
            f'contato@dellainstore.com.br'
        )

        msg = EmailMultiAlternatives(
            subject    = 'Redefinição de senha — Della Instore',
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [usuario.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        logger.info('E-mail de recuperação de senha enviado para %s', usuario.email)
        return True

    except Exception as exc:
        logger.error('Falha ao enviar e-mail de recuperação para %s: %s', usuario.email, exc)
        return False
