"""
Nouzové zrušení dvoufázového ověření (ztracený telefon i záložní kódy):
    python manage.py reset_2fa <uživatelské jméno>
Po dalším přihlášení si uživatel spáruje novou aplikaci.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.two_factor import remove_two_factor


class Command(BaseCommand):
    help = "Zruší spárovanou ověřovací aplikaci a záložní kódy uživatele."

    def add_arguments(self, parser):
        parser.add_argument('username')

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(f"Uživatel {options['username']} neexistuje.")
        remove_two_factor(user)
        self.stdout.write(self.style.SUCCESS(
            f"2FA pro {user.username} zrušeno. Při příštím přihlášení si spáruje novou aplikaci."
        ))
