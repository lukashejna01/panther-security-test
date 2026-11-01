"""
Nastavení pro automatické testy: SQLite v paměti, rychlé hashování hesel,
bez přesměrování na HTTPS. Spuštění:
    python manage.py test --settings=config.settings_test
"""

import os
import tempfile

os.environ.setdefault('SECRET_KEY', 'test-' + 'x' * 60)

from .settings import *  # noqa: E402,F401,F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
SECURE_SSL_REDIRECT = False
MEDIA_ROOT = tempfile.mkdtemp(prefix='panther-test-media-')
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'root': {'level': 'CRITICAL'}}

# Testy nesmí nikdy sáhnout na skutečnou datovou schránku
ISDS_USERNAME = ''
ISDS_PASSWORD = ''
