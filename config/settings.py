import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Načtení proměnných z .env (vedle manage.py, nezávisle na pracovním adresáři)
load_dotenv(BASE_DIR / '.env')

# Bez tajného klíče aplikace nenaběhne – žádný výchozí klíč v kódu,
# jinak by šlo podvrhnout session i odkazy pro reset hesla.
SECRET_KEY = os.getenv('SECRET_KEY', '')
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("V .env chybí SECRET_KEY (aspoň 50 znaků).")

DEBUG = False

# Lokální vývoj přes http://127.0.0.1 – v .env nastavit LOCAL_DEV=1.
# Na serveru nikdy, jinak se vypne přesměrování na HTTPS a HSTS.
LOCAL_DEV = os.getenv('LOCAL_DEV') == '1'

ALLOWED_HOSTS = ['www.panther-security.cz', 'panther-security.cz', 'webapp-3258159.pythonanywhere.com', 'localhost', '127.0.0.1']

# Aplikace projektu
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Zabezpečení: blokace hádání hesel a Content-Security-Policy
    'axes',
    'csp',
    # Dvoufázové ověření majitele (Google Authenticator) + záložní kódy
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',

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
    'django_otp.middleware.OTPMiddleware',
    'core.middleware.TwoFactorRequiredMiddleware',
    'core.middleware.ForcePasswordChangeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'csp.middleware.CSPMiddleware',
    # Musí být poslední – převádí zablokované přihlášení na stránku s hláškou
    'axes.middleware.AxesMiddleware',
]

AUTHENTICATION_BACKENDS = [
    # Musí být první – při zablokování odmítne přihlášení dřív, než se ověří heslo
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
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
            # Filtr |kc pro částky (1 234,50) dostupný ve všech šablonách
            'builtins': ['core.templatetags.money'],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Databáze: na serveru MySQL na PythonAnywhere. Ta není zvenku dostupná, proto se
# při lokálním vývoji (LOCAL_DEV=1) použije místní SQLite soubor db.sqlite3.
if LOCAL_DEV:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
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

# Pravidla pro hesla (uplatní se při změně hesla v profilu a v administraci)
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Zabezpečení HTTPS, cookies a hlaviček
# PythonAnywhere ukončuje HTTPS na svém proxy a předává X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = not LOCAL_DEV
SECURE_HSTS_SECONDS = 0 if LOCAL_DEV else 60 * 60 * 24 * 365
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

SESSION_COOKIE_SECURE = not LOCAL_DEV
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 60 * 60 * 10  # odhlášení po 10 hodinách (jedna směna dispečera)
CSRF_COOKIE_SECURE = not LOCAL_DEV
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = ['https://www.panther-security.cz', 'https://panther-security.cz']

# Ochrana proti hádání hesel (django-axes): 5 chybných pokusů na stejný účet
# ze stejné IP adresy = blokace na 30 minut. Úspěšné přihlášení počítadlo nuluje.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.5  # hodiny
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_RESET_ON_SUCCESS = True
AXES_CLIENT_IP_CALLABLE = 'core.client_ip.get_client_ip'
AXES_LOCKOUT_TEMPLATE = 'auth/locked_out.html'

# Dvoufázové ověření: název účtu v aplikaci Google Authenticator
OTP_TOTP_ISSUER = 'Panther Security'

# Administrace na nenápadné adrese – v .env nastavit např. ADMIN_URL=sprava-7f3k9/
ADMIN_URL = os.getenv('ADMIN_URL', 'admin/')

# Content-Security-Policy: prohlížeč načte skripty, styly a obrázky jen z našeho
# webu (+ písma Google Fonts) a stránku nepůjde vložit do cizího webu.
# 'unsafe-inline' je zatím nutné kvůli skriptům a stylům přímo v šablonách.
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'"],
        'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
        'font-src': ["'self'", 'https://fonts.gstatic.com'],
        'img-src': ["'self'", 'data:'],
        'connect-src': ["'self'"],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
        'frame-ancestors': ["'none'"],
    },
}

# Logování do error logu PythonAnywhere (Web → Log files). Bez toho se při
# DEBUG = False chyby serveru ani bezpečnostní události nikam nezapisují.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR'},
        'django.security': {'handlers': ['console'], 'level': 'WARNING'},
        'axes': {'handlers': ['console'], 'level': 'WARNING'},
        'core': {'handlers': ['console'], 'level': 'INFO'},
        'web': {'handlers': ['console'], 'level': 'INFO'},
    },
}

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
# Den, od kterého je firma u ČSSZ registrovaná jako zaměstnavatel (RRRR-MM-DD).
# Nástup před tímto dnem ČSSZ odmítne (chyba 103901619), aplikace to proto hlídá předem.
COMPANY_CSSZ_EMPLOYER_SINCE = os.getenv('COMPANY_CSSZ_EMPLOYER_SINCE', '')

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
# VS od ČSSZ pro testovací prostředí – prázdné = testovací podání vypnuté
CSSZ_TEST_VS = os.getenv('CSSZ_TEST_VS', '')
# Kód OSSZ k testovacímu VS – prázdné = stejný jako COMPANY_CSSZ_DEP
CSSZ_TEST_DEP = os.getenv('CSSZ_TEST_DEP', '')

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