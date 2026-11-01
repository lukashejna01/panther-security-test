"""
Middleware pro vynucení změny dočasného hesla po prvním přihlášení.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


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
