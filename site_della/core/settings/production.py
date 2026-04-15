"""
Settings de PRODUÇÃO — herda de base.py
Ativa todas as camadas de segurança do Django.
"""

from .base import *  # noqa

DEBUG = False

# ─── Segurança HTTP ───────────────────────────────────────────────────────────

# Força HTTPS — redireciona HTTP para HTTPS
SECURE_SSL_REDIRECT = True

# HSTS: instrui o browser a sempre usar HTTPS por 1 ano
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie de sessão só trafega via HTTPS
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'   # proteção CSRF cross-site

# Cookie CSRF só via HTTPS
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # False permite que JS leia o token para chamadas AJAX
CSRF_COOKIE_SAMESITE = 'Lax'

# Origens confiáveis para CSRF (M2 — obrigatório com HTTPS e proxy reverso)
CSRF_TRUSTED_ORIGINS = [
    'https://novo.dellainstore.com.br',
    'https://www.dellainstore.com.br',
    'https://dellainstore.com.br',
    'https://www.dellainstore.com',
    'https://dellainstore.com',
]

# Bloqueia conteúdo mixed HTTP/HTTPS
SECURE_BROWSER_XSS_FILTER = True

# Impede sniffing de MIME type pelo browser
SECURE_CONTENT_TYPE_NOSNIFF = True

# Impede que a página seja carregada em iframe (anti-clickjacking)
X_FRAME_OPTIONS = 'DENY'

# Referrer controlado — não vaza URL interna para sites externos
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Permissões do browser (câmera, microfone, geolocalização) — tudo bloqueado
PERMISSIONS_POLICY = {
    'camera': [],
    'microphone': [],
    'geolocation': [],
    'payment': ['self'],
}

# ─── Proxy reverso Nginx ──────────────────────────────────────────────────────

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# ─── Logging em produção ──────────────────────────────────────────────────────
# Erros vão para arquivo — NUNCA exibir traceback para o usuário

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django_error.log',
            'maxBytes': 1024 * 1024 * 5,  # 5MB por arquivo
            'backupCount': 3,
            'formatter': 'verbose',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 3,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
        'axes': {
            'handlers': ['file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
