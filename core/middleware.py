"""
Middleware pro vynucení dvoufázového ověření majitele a změny dočasného hesla.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from core.two_factor import has_two_factor, requires_two_factor


class TwoFactorRequiredMiddleware:
    """
    Majitel (a superuživatel) se po přihlášení heslem dostane jen na zadání
    kódu z aplikace, případně na první spárování – dokud se neověří.
    Musí být za django_otp.middleware.OTPMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if requires_two_factor(user) and not user.is_verified():
            target = 'two_factor_verify' if has_two_factor(user) else 'two_factor_setup'
            allowed = (reverse('two_factor_verify'), reverse('two_factor_setup'), reverse('logout'))
            if request.path not in allowed:
                return redirect(f"{reverse(target)}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    """
    Uživatel s dočasným heslem od manažera se dostane jen na profil
    (změna hesla) a odhlášení, dokud si heslo nezmění.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            profile = getattr(user, 'employee_profile', None)
            allowed = (reverse('user_profile'), reverse('logout'))
            if profile and profile.must_change_password and request.path not in allowed:
                messages.warning(request, "Před pokračováním si prosím nastavte vlastní heslo.")
                return redirect('user_profile')
        return self.get_response(request)
