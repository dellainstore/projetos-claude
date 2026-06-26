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

# Banco separado somente-leitura do app produtos (SQLite existente)
PRODUTOS_DB_PATH = os.getenv(
    "PRODUTOS_DB_PATH",
    "/var/www/della-sistemas/app/produtos/data/inclusoes.db",
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

SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 horas
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

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
    },
}
