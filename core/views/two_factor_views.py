"""
Pohledy pro dvoufázové ověření majitele: spárování aplikace, zadání kódu
po přihlášení a nové spárování při ztrátě telefonu.
"""

import base64
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp import devices_for_user, match_token
from django_otp.plugins.otp_static.models import StaticDevice

from core.client_ip import get_client_ip
from core.qr import qr_code_data_uri
from core.two_factor import (
    create_backup_codes,
    has_two_factor,
    pending_totp_device,
    remove_two_factor,
    requires_two_factor,
)
from .auth_views import redirect_user_by_role

logger = logging.getLogger(__name__)


def _safe_next(request):
    """Adresa, kam pokračovat po ověření – jen v rámci našeho webu, jinak None."""
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return None


def _continue(request):
    """Po ověření zpět na původně požadovanou stránku, jinak do portálu podle role."""
    next_url = _safe_next(request)
    return redirect(next_url) if next_url else redirect_user_by_role(request.user)


def _clean_code(raw):
    return ''.join(raw.split()).lower()


def _throttle_wait_seconds(devices):
    """
    Po chybném kódu django-otp na chvíli (1, 2, 4, 8 … s) blokuje další pokus –
    i správný kód by pak neprošel. Vrátí, kolik sekund zbývá čekat (0 = lze zkoušet).
    """
    wait = 0
    for device in devices:
        allowed, data = device.verify_is_allowed()
        if not allowed and data and data.get('locked_until'):
            wait = max(wait, int((data['locked_until'] - timezone.now()).total_seconds()) + 1)
    return wait


@login_required
def two_factor_setup_view(request):
    """Spárování Google Authenticatoru (QR kód) a vydání záložních kódů."""
    user = request.user
    if not requires_two_factor(user):
        return redirect_user_by_role(user)
    # Už spárovaný účet nejde přepárovat jen s heslem – jinak by si útočník
    # se zjištěným heslem přidal vlastní telefon.
    if has_two_factor(user):
        return redirect('two_factor_verify')

    device = pending_totp_device(user)
    if request.method == 'POST':
        wait = _throttle_wait_seconds([device])
        if wait:
            messages.error(request, f"Po chybném kódu počkejte {wait} s a zadejte aktuální kód znovu.")
        elif device.verify_token(_clean_code(request.POST.get('code', ''))):
            device.confirmed = True
            device.save(update_fields=['confirmed'])
            otp_login(request, device)
            request.session.cycle_key()
            codes = create_backup_codes(user)
            logger.warning("2FA: uživatel %s spároval ověřovací aplikaci (IP %s)", user.username, get_client_ip(request))
            response = render(request, 'auth/two_factor_backup_codes.html', {
                'codes': codes,
                'continue_url': _safe_next(request) or redirect_user_by_role(user).url,
            })
            add_never_cache_headers(response)
            return response
        else:
            messages.error(request, "Kód nesouhlasí. Zkontrolujte čas v telefonu a zadejte aktuální kód.")

    secret = base64.b32encode(device.bin_key).decode()
    response = render(request, 'auth/two_factor_setup.html', {
        'qr_code': qr_code_data_uri(device.config_url),
        'secret': ' '.join(secret[i:i + 4] for i in range(0, len(secret), 4)),
        'next': request.GET.get('next', ''),
    })
    add_never_cache_headers(response)
    return response


@login_required
def two_factor_verify_view(request):
    """Zadání kódu z aplikace (nebo záložního kódu) po přihlášení heslem."""
    user = request.user
    if not requires_two_factor(user) or user.is_verified():
        return _continue(request)
    if not has_two_factor(user):
        return redirect('two_factor_setup')

    if request.method == 'POST':
        wait = _throttle_wait_seconds(devices_for_user(user))
        if wait:
            messages.error(request, f"Po chybném kódu počkejte {wait} s a zadejte aktuální kód znovu.")
            return render(request, 'auth/two_factor_verify.html', {'next': request.POST.get('next', '')})
        device = match_token(user, _clean_code(request.POST.get('code', '')))
        if device:
            otp_login(request, device)
            request.session.cycle_key()
            if isinstance(device, StaticDevice):
                remaining = device.token_set.count()
                logger.warning("2FA: uživatel %s použil záložní kód, zbývá %s", user.username, remaining)
                messages.warning(request, f"Přihlásili jste se záložním kódem, zbývá jich {remaining}. Pokud jste ztratili telefon, spárujte v profilu novou aplikaci.")
            return _continue(request)
        logger.warning("2FA: chybný kód pro uživatele %s (IP %s)", user.username, get_client_ip(request))
        messages.error(request, "Neplatný kód. Zkuste to znovu – po opakovaných chybách se další pokus na chvíli zablokuje.")

    return render(request, 'auth/two_factor_verify.html', {'next': request.GET.get('next', '')})


@login_required
@require_POST
def two_factor_reset_view(request):
    """Nové spárování (ztráta / výměna telefonu) – jen z již ověřené relace."""
    user = request.user
    if not requires_two_factor(user) or not user.is_verified():
        return redirect('two_factor_verify')
    remove_two_factor(user)
    logger.warning("2FA: uživatel %s zrušil spárovanou aplikaci (IP %s)", user.username, get_client_ip(request))
    messages.info(request, "Stará aplikace i záložní kódy přestaly platit. Naskenujte nový QR kód.")
    return redirect('two_factor_setup')
