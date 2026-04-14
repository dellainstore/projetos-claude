"""
Bling OAuth2 — fluxo Authorization Code para a API v3.

Referência: https://developer.bling.com.br/autenticacao
"""

import base64
import logging
import secrets

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

AUTHORIZE_URL = 'https://www.bling.com.br/Api/v3/oauth/authorize'
TOKEN_URL     = 'https://api.bling.com.br/Api/v3/oauth/token'


def _b64_credentials() -> str:
    """Retorna base64(client_id:client_secret) para o header Authorization."""
    raw = f'{settings.BLING_CLIENT_ID}:{settings.BLING_CLIENT_SECRET}'
    return base64.b64encode(raw.encode()).decode()


def get_authorize_url(redirect_uri: str, state: str | None = None) -> str:
    """Gera a URL para redirecionar o usuário ao Bling para autorizar."""
    if state is None:
        state = secrets.token_urlsafe(16)
    params = (
        f'?response_type=code'
        f'&client_id={settings.BLING_CLIENT_ID}'
        f'&redirect_uri={redirect_uri}'
        f'&state={state}'
    )
    return AUTHORIZE_URL + params


def exchange_code(code: str, redirect_uri: str):
    """
    Troca o authorization code por access_token + refresh_token.
    Salva o BlingToken no banco e retorna o objeto salvo.
    """
    from .models import BlingToken

    resp = requests.post(
        TOKEN_URL,
        headers={
            'Authorization': f'Basic {_b64_credentials()}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        },
        data={
            'grant_type':   'authorization_code',
            'code':         code,
            'redirect_uri': redirect_uri,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return _salvar_token(data)


def refresh_token(token_obj):
    """
    Usa o refresh_token para obter um novo access_token.
    Atualiza o objeto BlingToken existente no banco.
    """
    resp = requests.post(
        TOKEN_URL,
        headers={
            'Authorization': f'Basic {_b64_credentials()}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        },
        data={
            'grant_type':    'refresh_token',
            'refresh_token': token_obj.refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return _salvar_token(data, token_obj)


def get_valid_access_token() -> str | None:
    """
    Retorna um access_token válido, fazendo refresh se necessário.
    Retorna None se não houver token salvo ou se o refresh falhar.
    """
    from .models import BlingToken

    token = BlingToken.objects.order_by('-criado_em').first()
    if not token:
        logger.warning('Bling: nenhum token salvo. Execute a autorização OAuth.')
        return None

    if not token.valido:
        logger.info('Bling: access_token expirado, tentando refresh...')
        try:
            token = refresh_token(token)
        except requests.HTTPError as exc:
            body = ''
            try:
                body = exc.response.text or ''
            except Exception:
                pass

            if 'invalid_grant' in body or 'Invalid refresh token' in body:
                logger.error(
                    'Bling: refresh_token inválido/expirado. '
                    'Acesse /bling/autorizar/ para re-autorizar a integração.'
                )
            else:
                logger.error('Bling: falha no refresh_token: %s', exc)
            return None
        except Exception as exc:
            logger.error('Bling: falha inesperada no refresh_token: %s', exc)
            return None

    return token.access_token


def _salvar_token(data: dict, token_obj=None):
    """Salva/atualiza o BlingToken no banco."""
    from .models import BlingToken

    expira_em = timezone.now() + timezone.timedelta(seconds=data.get('expires_in', 3600))

    if token_obj:
        token_obj.access_token  = data['access_token']
        token_obj.refresh_token = data['refresh_token']
        token_obj.expira_em     = expira_em
        token_obj.save()
        return token_obj

    return BlingToken.objects.create(
        access_token  = data['access_token'],
        refresh_token = data['refresh_token'],
        expira_em     = expira_em,
    )
