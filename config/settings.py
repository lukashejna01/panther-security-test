import os
from pathlib import Path
from dotenv import load_dotenv

# Načtení proměnných z .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'panther-security-default-dev-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')]

# Aplikace projektu
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Naše aplikace
    'core',
    'web',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Databáze (pro vývoj SQLite)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Lokalizace pro ČR
LANGUAGE_CODE = 'cs'
TIME_ZONE = 'Europe/Prague'
USE_I18N = True
USE_TZ = True

# Statické soubory & média
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# Konfigurace externích API a firemní údaje
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Panther Security s.r.o.')
COMPANY_ICO = os.getenv('COMPANY_ICO', '22525882')
COMPANY_DIC = os.getenv('COMPANY_DIC', 'CZ22525882')
COMPANY_STREET = os.getenv('COMPANY_STREET', '')
COMPANY_CITY = os.getenv('COMPANY_CITY', '')
COMPANY_ZIP = os.getenv('COMPANY_ZIP', '')
COMPANY_BANK_ACCOUNT = os.getenv('COMPANY_BANK_ACCOUNT', '')
COMPANY_BANK_CODE = os.getenv('COMPANY_BANK_CODE', '')
COMPANY_CSSZ_VS = os.getenv('COMPANY_CSSZ_VS', '8862067306')
COMPANY_CSSZ_DEP = os.getenv('COMPANY_CSSZ_DEP', '886')