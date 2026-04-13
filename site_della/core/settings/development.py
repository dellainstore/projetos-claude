"""
Settings de DESENVOLVIMENTO — herda de base.py
DEBUG ativo, sem HTTPS, sem bloqueio de brute force agressivo.
"""

from .base import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# ─── Banco em desenvolvimento ─────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'della_site_dev',
        'USER': 'della_user',
        'PASSWORD': 'dev_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# ─── E-mail em desenvolvimento (console) ─────────────────────────────────────
# Exibe e-mails no terminal — sem enviar de verdade

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ─── Brute force mais permissivo em dev ──────────────────────────────────────

AXES_FAILURE_LIMIT = 100
AXES_ENABLED = False  # desativa em desenvolvimento

# ─── Sem HTTPS obrigatório em dev ────────────────────────────────────────────

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# ─── CSP relaxada em dev (facilita debug) ────────────────────────────────────

CSP_DEFAULT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'", "*")

# ─── Logging em desenvolvimento ──────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',  # mostra queries SQL no terminal
            'propagate': False,
        },
        'axes': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
