import os
from pathlib import Path
from dotenv import load_dotenv

# Načtení proměnných z .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'panther-security-default-dev-key')
DEBUG = False

ALLOWED_HOSTS = ['www.panther-security.cz', 'panther-security.cz', 'webapp-3258159.pythonanywhere.com', 'localhost', '127.0.0.1']

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
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'panthersec$panther',
        'USER': 'panthersec',
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': 'panthersec.mysql.pythonanywhere-services.com',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
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
# Cíl pro collectstatic (na PythonAnywhere namapovat /static/ sem)
STATIC_ROOT = BASE_DIR / 'staticfiles'

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
COMPANY_STREET = os.getenv('COMPANY_STREET') or 'Varšavská 715/36'
COMPANY_CITY = os.getenv('COMPANY_CITY') or 'Praha 2'
COMPANY_ZIP = os.getenv('COMPANY_ZIP') or '120 00'
COMPANY_BANK_ACCOUNT = os.getenv('COMPANY_BANK_ACCOUNT', '')
COMPANY_BANK_CODE = os.getenv('COMPANY_BANK_CODE', '')
COMPANY_CSSZ_VS = os.getenv('COMPANY_CSSZ_VS', '8862067306')
COMPANY_CSSZ_DEP = os.getenv('COMPANY_CSSZ_DEP', '886')

# Místo podpisu ve smlouvách ("V Praze dne ...") – v 6. pádě
CONTRACT_SIGN_PLACE = os.getenv('CONTRACT_SIGN_PLACE', 'Praze')

# ČSSZ – registrace zaměstnance (REGZEC)
# Kód profese podle CZ-ISCO (5 číslic) pro strážného – nutno doplnit
CSSZ_PROFESSION_CODE = os.getenv('CSSZ_PROFESSION_CODE', '')
# Pracovní režim: 1 jednosměnný, 2 dvousměnný, 3 vícesměnný, 4 neuvedeno
CSSZ_WORK_MODE = os.getenv('CSSZ_WORK_MODE', '3')
# Nepřetržitý provoz: A / N
CSSZ_CONTINUOUS_OPERATION = os.getenv('CSSZ_CONTINUOUS_OPERATION', 'A')
# Výchozí obec výkonu práce (název a šestimístný kód obce ZÚJ)
CSSZ_DEFAULT_MUNICIPALITY = os.getenv('CSSZ_DEFAULT_MUNICIPALITY', 'Praha')
CSSZ_DEFAULT_MUNICIPALITY_CODE = os.getenv('CSSZ_DEFAULT_MUNICIPALITY_CODE', '554782')
# Fiktivní VS od ČSSZ pro testovací prostředí (začíná 999) – prázdné = testovací XML vypnuté
CSSZ_TEST_VS = os.getenv('CSSZ_TEST_VS', '')

# Datová schránka (ISDS) pro odesílání podání na ČSSZ přímo z aplikace
# ISDS_ENVIRONMENT: "test" = testovací datovky, "prod" = ostré
ISDS_ENVIRONMENT = os.getenv('ISDS_ENVIRONMENT', 'test')
ISDS_USERNAME = os.getenv('ISDS_USERNAME', '')
ISDS_PASSWORD = os.getenv('ISDS_PASSWORD', '')
# Volitelně jiná adresa služeb (jinak ws1.datovka.gov.cz / ws1.datovka-test.gov.cz)
ISDS_HOST = os.getenv('ISDS_HOST', '')
# Datové schránky ČSSZ pro registraci zaměstnance: ostrá 5ffu6xk, testovací 9tsaf6s
CSSZ_DATABOX_PROD = os.getenv('CSSZ_DATABOX_PROD', '5ffu6xk')
CSSZ_DATABOX_TEST = os.getenv('CSSZ_DATABOX_TEST', '9tsaf6s')