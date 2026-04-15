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
]

LOCAL_APPS = [
    'apps.conteudo',    # banners, mini banners, look da semana
    'apps.produtos',
    'apps.pedidos',
    'apps.pagamentos',
    'apps.bling',
    'apps.usuarios',
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
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # anti-clickjacking
    'axes.middleware.AxesMiddleware',                  # brute force protection
    'csp.middleware.CSPMiddleware',                    # Content-Security-Policy
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
MAX_UPLOAD_SIZE_MB = 5  # máximo 5MB por imagem

# ─── E-mail ───────────────────────────────────────────────────────────────────

EMAIL_BACKEND     = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST        = config('EMAIL_HOST', default='smtps.uhserver.com')
EMAIL_PORT        = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_SSL     = config('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_USE_TLS     = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_HOST_USER   = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Della Instore <contato@dellainstore.com.br>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ─── django-axes: bloqueio de brute force ─────────────────────────────────────

AXES_FAILURE_LIMIT = 5           # bloqueia após 5 tentativas falhas
AXES_COOLOFF_TIME = 1            # bloqueia por 1 hora
AXES_LOCKOUT_TEMPLATE = 'components/lockout.html'
AXES_RESET_ON_SUCCESS = True     # reseta contador após login bem-sucedido
# Bloqueia por IP + username (não só por usuário)
AXES_LOCKOUT_PARAMETERS = ['ip_address', 'username']

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
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
            "'unsafe-inline'",          # necessário para Tailwind CDN
            "cdn.tailwindcss.com",
            "cdnjs.cloudflare.com",
            "www.instagram.com",
            "connect.facebook.net",
        ),
        'style-src': (
            "'self'",
            "'unsafe-inline'",          # inline styles do Tailwind
            "fonts.googleapis.com",
            "cdnjs.cloudflare.com",
        ),
        'font-src': (
            "'self'",
            "fonts.gstatic.com",
            "fonts.googleapis.com",
            "cdnjs.cloudflare.com",
        ),
        'img-src': (
            "'self'",
            "data:",
            "*.instagram.com",
            "cdninstagram.com",
            "*.cdninstagram.com",
        ),
        'frame-src': (
            "'self'",
            "www.instagram.com",
            "www.youtube.com",
        ),
        'connect-src': ("'self'",),
        'object-src': ("'none'",),      # bloqueia Flash e plugins antigos
    }
}

# ─── Integrações externas ─────────────────────────────────────────────────────

PAGSEGURO_EMAIL = config('PAGSEGURO_EMAIL', default='')
PAGSEGURO_TOKEN = config('PAGSEGURO_TOKEN', default='')
PAGSEGURO_SANDBOX = config('PAGSEGURO_SANDBOX', default=True, cast=bool)

STONE_CLIENT_ID = config('STONE_CLIENT_ID', default='')
STONE_CLIENT_SECRET = config('STONE_CLIENT_SECRET', default='')
STONE_SANDBOX = config('STONE_SANDBOX', default=True, cast=bool)

SITE_URL = config('SITE_URL', default='http://159.203.101.232:8000')

BLING_CLIENT_ID     = config('BLING_CLIENT_ID', default='')
BLING_CLIENT_SECRET = config('BLING_CLIENT_SECRET', default='')
BLING_REDIRECT_URI  = config('BLING_REDIRECT_URI', default='http://localhost:8000/bling/callback/')

WHATSAPP_NUMBER_1 = config('WHATSAPP_NUMBER_1', default='')
WHATSAPP_NUMBER_2 = config('WHATSAPP_NUMBER_2', default='')

INSTAGRAM_ACCESS_TOKEN = config('INSTAGRAM_ACCESS_TOKEN', default='')
INSTAGRAM_APP_ID       = config('INSTAGRAM_APP_ID', default='')
INSTAGRAM_APP_SECRET   = config('INSTAGRAM_APP_SECRET', default='')

MELHOR_ENVIO_TOKEN   = config('MELHOR_ENVIO_TOKEN', default='')
MELHOR_ENVIO_SANDBOX = config('MELHOR_ENVIO_SANDBOX', default=True, cast=bool)

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
