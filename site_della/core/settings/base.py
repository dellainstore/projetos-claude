"""
Settings base — compartilhado entre development e production.
Nunca importar diretamente: use base.py apenas como herança.
"""

import os
from pathlib import Path
from decouple import config, Csv

# ─── Caminhos ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Segurança principal ──────────────────────────────────────────────────────

SECRET_KEY = config('SECRET_KEY')

# Lista explícita de hosts — NUNCA usar '*' em produção
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# ─── Apps instalados ──────────────────────────────────────────────────────────

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'axes',        # bloqueio de brute force em login
    'csp',         # Content-Security-Policy headers
    'anymail',     # e-mail transacional via API (Brevo)
]

LOCAL_APPS = [
    'apps.conteudo',    # banners, mini banners, look da semana
    'apps.produtos',
    'apps.pedidos',
    'apps.pagamentos',
    'apps.bling',
    'apps.usuarios',
    'apps.core_utils',  # utilitários compartilhados (cache, sanitize, management commands)
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware — ordem importa ───────────────────────────────────────────────

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',      # static em produção
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',       # proteção CSRF ativa
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core_utils.maintenance.manutencao_middleware',
    'apps.core_utils.admin_verificacao.AdminVerificacaoMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # anti-clickjacking
    'axes.middleware.AxesMiddleware',                  # brute force protection
    'csp.middleware.CSPMiddleware',                    # Content-Security-Policy
    'apps.core_utils.middleware.MetaCAPIPageViewMiddleware',  # CAPI PageView sempre
]

ROOT_URLCONF = 'core.urls'

# ─── Templates ────────────────────────────────────────────────────────────────

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.produtos.context_processors.categorias_menu',
                'apps.produtos.context_processors.newsletter_status',
                'apps.pedidos.context_processors.carrinho_info',
            ],
            # auto-escape ativo por padrão — nunca usar |safe sem necessidade
            'autoescape': True,
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ─── Banco de dados ───────────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='della_site'),
        'USER': config('DB_USER', default='della_user'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'OPTIONS': {
            'connect_timeout': 10,
        },
        'CONN_MAX_AGE': 60,  # pool de conexões — economiza memória no VPS
    }
}

# ─── Validação de senha de usuários ───────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Autenticação ─────────────────────────────────────────────────────────────

AUTH_USER_MODEL = 'usuarios.Cliente'

LOGIN_URL = '/conta/entrar/'
LOGIN_REDIRECT_URL = '/conta/minha-conta/'
LOGOUT_REDIRECT_URL = '/'

# ─── Internacionalização ──────────────────────────────────────────────────────

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# ─── Arquivos estáticos ───────────────────────────────────────────────────────

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Django 5.x usa STORAGES (dict); STATICFILES_STORAGE sozinho é ignorado.
# Storage custom (core.storage) = CompressedManifestStaticFilesStorage com
# manifest_strict=False → gera hashes nos nomes (cache-busting no mobile)
# sem quebrar a página se algum {% static %} referencia arquivo faltante.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'core.storage.WhiteNoiseManifestStorageLeniente',
    },
}

# ─── Media (uploads) ──────────────────────────────────────────────────────────

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Extensões permitidas para upload de imagens de produto
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
MAX_UPLOAD_SIZE_MB = 15  # máximo 15MB por imagem (fotos de produto profissionais)

# ─── E-mail (Brevo via API HTTP — porta 443, não bloqueada pela Digital Ocean) ──

EMAIL_BACKEND  = 'anymail.backends.brevo.EmailBackend'
ANYMAIL = {
    'BREVO_API_KEY': config('BREVO_API_KEY', default=''),
}
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default="D'ELLA Instore <contato@dellainstore.com.br>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# E-mails que recebem notificacao de formulario de contato do site (separados por virgula)
CONTATO_NOTIF_EMAILS  = config('CONTATO_NOTIF_EMAILS',  default='contato@dellainstore.com.br,financeiro@dellainstore.com.br')
# E-mails que recebem o relatorio diario de seguranca
SECURITY_NOTIF_EMAILS = config('SECURITY_NOTIF_EMAILS', default='financeiro@dellainstore.com.br')

# django-axes: bloqueio de brute force

AXES_ENABLED = True              # explicito, sobrescrito para False em development.py
AXES_FAILURE_LIMIT = 5           # bloqueia apos 5 tentativas falhas
AXES_COOLOFF_TIME = 1            # bloqueia por 1 hora
AXES_LOCKOUT_TEMPLATE = 'components/lockout.html'
AXES_RESET_ON_SUCCESS = True     # reseta contador apos login bem-sucedido
# Bloqueia por IP + username
AXES_LOCKOUT_PARAMETERS = ['ip_address', 'username']
# Atras de Cloudflare + nginx (com real_ip do CF-Connecting-IP), o IP real
# vem em X-Real-IP / X-Forwarded-For. REMOTE_ADDR aqui aponta para o socket
# unix do gunicorn, entao precisamos instruir o ipware a olhar nos headers.
AXES_IPWARE_META_PRECEDENCE_ORDER = ['HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']
AXES_IPWARE_PROXY_COUNT = 1

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'apps.usuarios.backends.EmailOuCPFBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ─── Content-Security-Policy (django-csp 4.0+) ───────────────────────────────
# Restringe de onde o browser pode carregar scripts, estilos e imagens.
# Previne XSS mesmo que um payload seja injetado na página.

CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': ("'self'",),
        'script-src': (
            "'self'",
            "'unsafe-inline'",          # script fbclid em base.html (cookie _fbc para Meta)
            "connect.facebook.net",     # Meta Pixel
            "assets.pagseguro.com.br",  # SDK de encriptacao de cartao
            "www.googletagmanager.com", # GTM / GA4
            "www.clarity.ms",           # Microsoft Clarity
        ),
        'style-src': (
            "'self'",
            "'unsafe-inline'",          # estilos inline em templates e Django admin
        ),
        'font-src': (
            "'self'",                   # fontes auto-hospedadas em static/fonts/
        ),
        'img-src': (
            "'self'",
            "data:",
            "blob:",
            "*.instagram.com",
            "cdninstagram.com",
            "*.cdninstagram.com",
            "www.facebook.com",         # Meta Pixel tracking pixel
            "www.google-analytics.com", # GA4 beacons
            "www.googletagmanager.com",
        ),
        'frame-src': (
            "'self'",
            "www.instagram.com",
            "www.youtube.com",
        ),
        'connect-src': (
            "'self'",
            "assets.pagseguro.com.br",              # SDK PagBank
            "api.pagseguro.com",                    # API PagBank
            "buscacepinter.correios.com.br",        # busca de CEP no checkout
            "www.google-analytics.com",             # GA4 hits
            "region1.google-analytics.com",         # GA4 hits (datacenter alternativo)
            "analytics.google.com",
            "stats.g.doubleclick.net",              # GA4 / Ads
            "www.googletagmanager.com",
            "www.facebook.com",                     # Meta Pixel eventos
            "*.clarity.ms",                         # Microsoft Clarity beacons
            "c.bing.com",                           # Microsoft Clarity endpoint
        ),
        'object-src': ("'none'",),      # bloqueia Flash e plugins obsoletos
        'base-uri':   ("'self'",),      # impede injecao de <base href>
        'form-action': ("'self'",),     # formularios so submetem para o proprio site
        'report-uri': ('/csp-report/',),
    }
}

# ─── Integrações externas ─────────────────────────────────────────────────────

PAGSEGURO_EMAIL = config('PAGSEGURO_EMAIL', default='')
PAGSEGURO_TOKEN = config('PAGSEGURO_TOKEN', default='')
PAGSEGURO_TOKEN_SANDBOX = config('PAGSEGURO_TOKEN_SANDBOX', default='')
PAGSEGURO_SANDBOX = config('PAGSEGURO_SANDBOX', default=False, cast=bool)

SITE_URL = config('SITE_URL', default='https://www.dellainstore.com')

BLING_CLIENT_ID      = config('BLING_CLIENT_ID', default='')
BLING_CLIENT_SECRET  = config('BLING_CLIENT_SECRET', default='')
BLING_REDIRECT_URI   = config('BLING_REDIRECT_URI', default='https://www.dellainstore.com/bling/callback/')
# ID do depósito "Show Room - D'ella" no Bling — filtra o saldo de estoque por depósito.
# Descobrir em: Bling → Configurações → Depósitos, ou via GET /depositos na API.
BLING_DEPOSITO_ID    = config('BLING_DEPOSITO_ID', default='', cast=str)

WHATSAPP_NUMBER_1 = config('WHATSAPP_NUMBER_1', default='')
WHATSAPP_NUMBER_2 = config('WHATSAPP_NUMBER_2', default='')

META_PIXEL_ID = config('META_PIXEL_ID', default='')
GA_MEASUREMENT_ID = config('GA_MEASUREMENT_ID', default='')
# GA4 Measurement Protocol (disparo server-side do purchase no webhook de pagamento).
# Criar em: GA4 Admin > Fluxos de dados > Measurement Protocol API secrets.
GA_API_SECRET = config('GA_API_SECRET', default='')
CLARITY_PROJECT_ID = config('CLARITY_PROJECT_ID', default='')
META_CONVERSIONS_API_TOKEN = config('META_CONVERSIONS_API_TOKEN', default='')
META_CONVERSIONS_TEST_EVENT_CODE = config('META_CONVERSIONS_TEST_EVENT_CODE', default='')
META_GRAPH_API_VERSION = config('META_GRAPH_API_VERSION', default='v22.0')

INSTAGRAM_ACCESS_TOKEN = config('INSTAGRAM_ACCESS_TOKEN', default='')
INSTAGRAM_ACCOUNT_ID   = config('INSTAGRAM_ACCOUNT_ID', default='')
INSTAGRAM_APP_ID       = config('INSTAGRAM_APP_ID', default='')
INSTAGRAM_APP_SECRET   = config('INSTAGRAM_APP_SECRET', default='')

MELHOR_ENVIO_TOKEN          = config('MELHOR_ENVIO_TOKEN', default='')
MELHOR_ENVIO_SANDBOX        = config('MELHOR_ENVIO_SANDBOX', default=True, cast=bool)
MELHOR_ENVIO_CEP_ORIGEM     = config('MELHOR_ENVIO_CEP_ORIGEM', default='')
MELHOR_ENVIO_WEBHOOK_SECRET = config('MELHOR_ENVIO_WEBHOOK_SECRET', default='')

CORREIOS_USUARIO       = config('CORREIOS_USUARIO', default='')
CORREIOS_CODIGO_ACESSO = config('CORREIOS_CODIGO_ACESSO', default='')

# Chave Pix (CPF, CNPJ, e-mail, telefone ou chave aleatória)
PIX_CHAVE = config('PIX_CHAVE', default='')

# ─── Cache (arquivo — compatível com múltiplos workers Gunicorn) ─────────────

CACHES = {
    'default': {
        'BACKEND':  'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': BASE_DIR / 'cache',
        'TIMEOUT':  3600,   # 1 hora padrão
    }
}

# ─── Sessão ───────────────────────────────────────────────────────────────────

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 dias
SESSION_COOKIE_HTTPONLY = True            # JS não acessa o cookie de sessão
SESSION_SAVE_EVERY_REQUEST = False

# ─── Chave primária padrão ────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
