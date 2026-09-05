from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

_csrf_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "apps.core",
    "apps.produtos",
    "apps.metas",
    "apps.pedidos",
    "apps.analytics",
    "apps.rh",
    "apps.estoque",
    "apps.financeiro",
    "apps.tarefas",
    "apps.motoqueiro",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.static",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.ponto_pendencias",
                "apps.tarefas.context_processors.tarefas_pendencias",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

_della_site_db_pw = os.getenv("DELLA_SITE_DB_PASSWORD", "")
if _della_site_db_pw:
    DATABASES["della_site"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DELLA_SITE_DB_NAME", "della_site"),
        "USER": os.getenv("DELLA_SITE_DB_USER", "della_readonly"),
        "PASSWORD": _della_site_db_pw,
        "HOST": os.getenv("DELLA_SITE_DB_HOST", "localhost"),
        "PORT": os.getenv("DELLA_SITE_DB_PORT", "5432"),
        "OPTIONS": {"options": "-c default_transaction_read_only=on"},
        "CONN_MAX_AGE": 60,
        "TEST": {"NAME": None},
    }
    DATABASE_ROUTERS = ["apps.analytics.router.DellaSiteRouter"]

# Encurtador de link (Site > Gerar link). SITE_URL e o dominio publico do
# site_della; LINK_CURTO_SECRET tem que ser IDENTICO ao configurado la
# (apps/conteudo/views_link_curto.py), senao toda criacao de link curto
# recebe 403 e o painel cai no fallback (link completo, sem encurtar).
SITE_URL = os.getenv("SITE_URL", "https://www.dellainstore.com")
LINK_CURTO_SECRET = os.getenv("LINK_CURTO_SECRET", "")

# Meta Marketing API (painel Site > Anúncios). Token de leitura das campanhas
# (ads_read/ads_management) — não é o mesmo uso do token de Conversions API
# do site_della, mas pode ser o mesmo valor gerado (o token de sistema tem
# ambos os escopos).
META_ADS_ACCOUNT_ID = os.getenv("META_ADS_ACCOUNT_ID", "")
META_ADS_TOKEN = os.getenv("META_ADS_TOKEN", "")
META_ADS_API_VERSION = os.getenv("META_ADS_API_VERSION", "v22.0")

# Banco de dados do módulo produtos (SQLite — inclusoes.db)
PRODUTOS_DB_PATH = os.getenv(
    "PRODUTOS_DB_PATH",
    str(BASE_DIR / "data" / "produtos" / "inclusoes.db"),
)

# Banco de dados do módulo Estoque - Análise (SQLite — preço/custo, saldo, vendas)
ESTOQUE_DB_PATH = os.getenv(
    "ESTOQUE_DB_PATH",
    str(BASE_DIR / "data" / "estoque" / "estoque.db"),
)
ESTOQUE_HISTORICO_CONSOLIDADO_XLSX_PATH = os.getenv(
    "ESTOQUE_HISTORICO_CONSOLIDADO_XLSX_PATH",
    "/var/www/della-sistemas/data/cmv_consolidado.xlsx",
)
ESTOQUE_HISTORICO_CONSOLIDADO_SHEET = os.getenv("ESTOQUE_HISTORICO_CONSOLIDADO_SHEET", "Produtos_Mensal")
ESTOQUE_HISTORICO_BASE_INICIO = os.getenv("ESTOQUE_HISTORICO_BASE_INICIO", "2025-01-01")
ESTOQUE_REPOSICAO_COBERTURA_ALVO_DIAS = os.getenv("ESTOQUE_REPOSICAO_COBERTURA_ALVO_DIAS", "30")
ESTOQUE_REPOSICAO_LOTE_MINIMO_MODELO_COR = os.getenv("ESTOQUE_REPOSICAO_LOTE_MINIMO_MODELO_COR", "12")
ESTOQUE_REPOSICAO_LOTE_MINIMO_SKU = os.getenv("ESTOQUE_REPOSICAO_LOTE_MINIMO_SKU", "6")
ESTOQUE_REPOSICAO_ARREDONDAR_MULTIPLO_LOTE = os.getenv("ESTOQUE_REPOSICAO_ARREDONDAR_MULTIPLO_LOTE", "true")
ESTOQUE_REPOSICAO_PESO_HISTORICO_TAMANHO = os.getenv("ESTOQUE_REPOSICAO_PESO_HISTORICO_TAMANHO", "0.50")
ESTOQUE_REPOSICAO_PESO_ESTOQUE_TAMANHO = os.getenv("ESTOQUE_REPOSICAO_PESO_ESTOQUE_TAMANHO", "0.30")
ESTOQUE_REPOSICAO_PESO_MIX_BASE_TAMANHO = os.getenv("ESTOQUE_REPOSICAO_PESO_MIX_BASE_TAMANHO", "0.20")
ESTOQUE_REPOSICAO_MIX_BASE_TAMANHO = os.getenv(
    "ESTOQUE_REPOSICAO_MIX_BASE_TAMANHO", "PP:0.10,P:0.25,M:0.30,G:0.20,GG:0.15"
)

AUTH_USER_MODEL = "core.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.core.backends.CaseInsensitiveBackend",
]

# ── django-axes (proteção contra força bruta no login) ────────────────────────
AXES_FAILURE_LIMIT = 5          # bloqueia após 5 tentativas erradas
AXES_COOLOFF_TIME = 1           # desbloqueia automaticamente após 1 hora
AXES_RESET_ON_SUCCESS = True    # zera contador após login bem-sucedido
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]  # isola por usuário+IP

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 dias

# Nomes próprios (não os padrões "sessionid"/"csrftoken" do Django): o site_della
# usa SESSION_COOKIE_DOMAIN/CSRF_COOKIE_DOMAIN = ".dellainstore.com" (cobre todos
# os subdomínios). Com o nome padrão, quem já visitou o site principal carrega
# um cookie "sessionid" válido em *.dellainstore.com que colide com o nosso
# (restrito a este subdomínio) — o navegador manda os dois com o mesmo nome e o
# servidor pode ler o valor errado, deslogando o usuário mesmo após login válido
# (bug real: usuária nova com sessionid "estranho" do site principal, 2026-07-23).
SESSION_COOKIE_NAME = "della_sistemas_sessionid"
CSRF_COOKIE_NAME = "della_sistemas_csrftoken"
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# Sessão deslizante: cada acesso renova os 30 dias. Quem usa com frequência
# (ex.: app no celular para bater ponto) fica praticamente sempre logado;
# no desktop só pede senha de novo após 30 dias sem usar.
SESSION_SAVE_EVERY_REQUEST = True

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Segurança (produção) ──────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True

X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["stderr"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps.motoqueiro": {
            "handlers": ["stderr"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
