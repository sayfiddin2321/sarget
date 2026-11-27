"""
SargetCRM — Django sozlamalari.

Production'ga chiqarishdan oldin quyidagi environment o'zgaruvchilarni sozlang:
  DJANGO_SECRET_KEY, DJANGO_DEBUG=False, DJANGO_ALLOWED_HOSTS
"""
import os
from pathlib import Path
from decouple import Config, RepositoryEnv
from django.core.exceptions import ImproperlyConfigured
from django.contrib.messages import constants as message_constants

BASE_DIR = Path(__file__).resolve().parent.parent
_env_file = BASE_DIR / '.env'
env = Config(RepositoryEnv(str(_env_file))) if _env_file.exists() else Config({})

# ── Xavfsizlik ──────────────────────────────────────────────────────
SECRET_KEY = env(
    'DJANGO_SECRET_KEY',
    'django-insecure-sarget-crm-dev-key-CHANGE-IN-PRODUCTION-2026'
)
DEBUG = env('DJANGO_DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = [h.strip() for h in env('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1,testserver').split(',') if h.strip()]
if DEBUG and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('*')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'core',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.permissions.BusinessRoleMiddleware',
    'core.audit.AuditActorMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sargetcrm.urls'

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
                'core.context_processors.role',
            ],
        },
    },
]

WSGI_APPLICATION = 'sargetcrm.wsgi.application'

DB_ENGINE = env('DB_ENGINE', default='sqlite').strip().lower()


if DB_ENGINE in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="crm_sarget_db"),
            "USER": env("DB_USER", default="postgres"),
            "PASSWORD": env("DB_PASSWORD", default=""),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
            "CONN_MAX_AGE": env(
                "DB_CONN_MAX_AGE",
                default=60,
                cast=int
            ),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Yuklanadigan rasm hajmi cheklovi (5 MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
# Only expose Django through the trusted reverse proxy in production.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

MESSAGE_TAGS = {
    message_constants.DEBUG: 'debug',
    message_constants.INFO: 'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR: 'danger',
}

# Sessiya — 8 soatdan keyin avtomatik chiqish (xavfsizlik)
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

if not DEBUG:
    if SECRET_KEY.startswith('django-insecure-'):
        raise ImproperlyConfigured('Production uchun DJANGO_SECRET_KEY ni sozlang.')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env('DJANGO_SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = env('DJANGO_SECURE_HSTS_SECONDS', default=0, cast=int)
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_WEBHOOK_SECRET = env('TELEGRAM_WEBHOOK_SECRET', default='')
TELEGRAM_STAFF_CHAT_ID = env('TELEGRAM_STAFF_CHAT_ID', default='')
CRM_API_KEY = env('CRM_API_KEY', default='')

# Only management server commands launch background work, never AppConfig/WSGI imports.
TELEGRAM_BOT_MODE = env('TELEGRAM_BOT_MODE', default='auto').strip().lower()
TELEGRAM_PUBLIC_URL = env('TELEGRAM_PUBLIC_URL', default='').strip().rstrip('/')
# Optional public CRM address used by printed receipt verification links.
QR_VERIFY_BASE_URL = env('QR_VERIFY_BASE_URL', default='').strip().rstrip('/')
CRM_BACKGROUND_JOBS = env('CRM_BACKGROUND_JOBS', default=True, cast=bool)
