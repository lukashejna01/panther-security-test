"""
Dvoufázové ověření (TOTP – Google Authenticator apod.) pro majitele.
"""

from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.models import SystemRole

BACKUP_CODE_COUNT = 10


def requires_two_factor(user):
    """
    2FA je povinné pro majitele a superuživatele (ti mají přístup všude
    včetně administrace, takže bez 2FA by šlo ověření obejít).
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'employee_profile', None)
    return bool(profile and profile.system_role == SystemRole.OWNER)


def has_two_factor(user):
    """Má uživatel spárovanou aplikaci (potvrzené TOTP zařízení)?"""
    return TOTPDevice.objects.devices_for_user(user, confirmed=True).exists()


def pending_totp_device(user):
    """Rozpracované (zatím nepotvrzené) párování aplikace – při každém pokusu stejný klíč."""
    device = TOTPDevice.objects.devices_for_user(user, confirmed=False).first()
    return device or TOTPDevice.objects.create(user=user, name='Ověřovací aplikace', confirmed=False)


def create_backup_codes(user):
    """Nová sada jednorázových záložních kódů (staré přestanou platit)."""
    StaticDevice.objects.filter(user=user).delete()
    device = StaticDevice.objects.create(user=user, name='Záložní kódy')
    codes = [StaticToken.random_token() for _ in range(BACKUP_CODE_COUNT)]
    StaticToken.objects.bulk_create(StaticToken(device=device, token=code) for code in codes)
    return codes


def remove_two_factor(user):
    """Zruší spárovanou aplikaci i záložní kódy (ztráta telefonu)."""
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()
