"""
Verificação de e-mail a cada 30 dias para o painel admin D'ELLA.

Fluxo:
  1. Usuário faz login normalmente (email + senha) no Django admin
  2. Middleware intercepta a próxima requisição ao painel e verifica se há
     uma validação recente (< 30 dias) no banco de dados
  3. Se não verificado: redireciona para /painel/verificar/ que envia o OTP
  4. Usuário digita o código → verificação salva → acesso liberado por 30 dias
"""

import logging
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import timezone
from django.templatetags.static import static

logger = logging.getLogger(__name__)


_ADMIN_PREFIX = '/painel/'
_EXCLUDED = {
    '/painel/verificar/',
    '/painel/login/',
    '/painel/logout/',
    '/painel/jsi18n/',
    '/painel/password_change/',
}


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AdminVerificacaoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(_ADMIN_PREFIX):
            return self.get_response(request)

        # Normaliza para comparação (com ou sem barra final)
        path_norm = request.path.rstrip('/') + '/'
        if path_norm in _EXCLUDED or request.path in _EXCLUDED:
            return self.get_response(request)

        if not request.user.is_authenticated or not request.user.is_staff:
            return self.get_response(request)

        if _esta_verificado(request.user):
            return self.get_response(request)

        # Precisa verificar
        from urllib.parse import urlencode
        next_url = request.get_full_path()
        return redirect('/painel/verificar/?' + urlencode({'next': next_url}))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esta_verificado(user):
    from apps.usuarios.models import AdminVerificacao
    try:
        return AdminVerificacao.objects.get(user=user).verificado_recentemente()
    except AdminVerificacao.DoesNotExist:
        return False


def _gerar_codigo():
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def _enviar_codigo(user):
    from apps.usuarios.models import AdminCodigo
    from django.core.mail import send_mail

    # Invalida códigos anteriores não usados
    AdminCodigo.objects.filter(user=user, usado=False).update(usado=True)

    codigo = _gerar_codigo()
    expira_em = timezone.now() + timedelta(minutes=10)
    AdminCodigo.objects.create(user=user, codigo=codigo, expira_em=expira_em)

    logo_url = getattr(settings, 'SITE_URL', 'https://www.dellainstore.com') + static('images/brand/logo-della.png')

    try:
        send_mail(
            subject="Código de acesso — D'ELLA Painel",
            message=f'Seu código de verificação é: {codigo}\nEle expira em 10 minutos.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=_email_html(codigo, logo_url),
        )
        logger.info('Código OTP enviado para %s', user.email)
    except Exception as exc:
        logger.error('Falha ao enviar código OTP para %s: %s', user.email, exc)


def _email_html(codigo, logo_url):
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Código de acesso — D'ELLA Instore</title>
</head>
<body style="margin:0;padding:0;background:#f4f3f1;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f3f1;padding:40px 0 48px;">
  <tr>
    <td align="center">
      <table width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;">

        <tr>
          <td style="background:#ffffff;padding:32px 40px 20px;text-align:center;border-radius:8px 8px 0 0;">
            <img src="{logo_url}" alt="D'ELLA" width="80"
                 style="display:block;margin:0 auto 6px;">
            <div style="font-size:8px;font-weight:400;color:#b0a090;letter-spacing:5px;text-transform:uppercase;">
              I N S T O R E
            </div>
          </td>
        </tr>

        <tr>
          <td style="background:#ffffff;padding:0 40px;">
            <div style="height:1px;background:#e0d0b8;"></div>
          </td>
        </tr>

        <tr>
          <td style="background:#ffffff;padding:32px 40px 40px;text-align:center;border-radius:0 0 8px 8px;">
            <div style="font-size:11px;font-weight:600;color:#c9a96e;letter-spacing:3px;
                        text-transform:uppercase;margin-bottom:12px;">
              Verificação de Acesso
            </div>
            <div style="font-size:20px;font-weight:300;color:#1a1a1a;letter-spacing:.3px;margin-bottom:8px;">
              Seu código de acesso ao painel
            </div>
            <div style="font-size:13px;color:#888;line-height:1.6;margin-bottom:32px;">
              Use o código abaixo para concluir o acesso.<br>
              Ele é válido por <strong>10 minutos</strong>.
            </div>
            <div style="display:inline-block;padding:18px 44px;background:#f4f3f1;
                        border:1px solid #e0d0b8;border-radius:6px;
                        font-size:34px;font-weight:600;letter-spacing:14px;
                        color:#1a1a1a;font-family:monospace;margin-bottom:28px;">
              {codigo}
            </div>
            <div style="font-size:11px;color:#bbb;margin-top:4px;">
              Se você não solicitou este código, ignore este e-mail.
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# View de verificação
# ---------------------------------------------------------------------------

def admin_verificar_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('/painel/login/')

    # Já verificado recentemente? Vai direto
    if _esta_verificado(request.user):
        next_url = request.GET.get('next', '/painel/')
        if not next_url.startswith('/'):
            next_url = '/painel/'
        return redirect(next_url)

    error = None
    reenviado = False

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'reenviar':
            _enviar_codigo(request.user)
            reenviado = True
        else:
            from apps.usuarios.models import AdminCodigo, AdminVerificacao

            codigo_digitado = request.POST.get('codigo', '').strip()
            codigo_obj = AdminCodigo.objects.filter(
                user=request.user,
                codigo=codigo_digitado,
                usado=False,
                expira_em__gt=timezone.now(),
            ).first()

            if codigo_obj:
                codigo_obj.usado = True
                codigo_obj.save()

                AdminVerificacao.objects.update_or_create(
                    user=request.user,
                    defaults={'ultima_verificacao': timezone.now()},
                )

                next_url = request.GET.get('next', '/painel/')
                if not next_url.startswith('/'):
                    next_url = '/painel/'
                return redirect(next_url)
            else:
                error = 'Código inválido ou expirado.'
    else:
        # GET: envia código se não há um recente (evita re-envio em cada reload)
        from apps.usuarios.models import AdminCodigo
        tem_recente = AdminCodigo.objects.filter(
            user=request.user,
            usado=False,
            criado_em__gt=timezone.now() - timedelta(minutes=2),
        ).exists()
        if not tem_recente:
            _enviar_codigo(request.user)

    email_mascarado = _mascarar_email(request.user.email)
    return render(request, 'admin/login_verificar.html', {
        'error': error,
        'reenviado': reenviado,
        'email_mascarado': email_mascarado,
        'next': request.GET.get('next', '/painel/'),
    })


def _mascarar_email(email):
    """Ex: w*****@gmail.com"""
    try:
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            return f'{local[0]}*@{domain}'
        return f'{local[0]}{"*" * (len(local) - 1)}@{domain}'
    except Exception:
        return email
