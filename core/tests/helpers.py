"""Společné pomůcky pro testy: uživatelé podle rolí, ověřené 2FA, HTTPS požadavky."""

from django.contrib.auth.models import User
from django.test import Client
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.models import Employee, SystemRole

# Požadavky jako přes HTTPS na produkční doménu
HTTPS = {'HTTP_HOST': 'www.panther-security.cz', 'secure': True}


def make_employee(username, role=SystemRole.STAFF, password='Silne-Heslo-2026', **fields):
    user = User.objects.create_user(username, password=password)
    defaults = {'first_name': username.capitalize(), 'last_name': 'Test', 'system_role': role}
    return Employee.objects.create(user=user, **{**defaults, **fields})


def logged_in_client(employee, verify_2fa=True):
    """Přihlášený klient; u majitele rovnou s ověřeným druhým faktorem."""
    client = Client()
    client.force_login(employee.user)
    if verify_2fa and employee.system_role == SystemRole.OWNER:
        device = TOTPDevice.objects.create(user=employee.user, name='test', confirmed=True)
        session = client.session
        session['otp_device_id'] = device.persistent_id
        session.save()
    return client
