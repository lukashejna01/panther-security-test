"""
Dekorátory pro ověřování systémových rolí uživatelů (STAFF, MANAGER, OWNER).
"""

from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from core.models import SystemRole


def role_required(allowed_roles):
    """
    Ověří, zda má přihlášený uživatel jednu z povolených rolí.
    Superuser má automatický přístup všude.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            profile = getattr(request.user, 'employee_profile', None)
            if profile and profile.system_role in allowed_roles:
                return view_func(request, *args, **kwargs)

            messages.error(request, "K této operaci nemáte dostatečná oprávnění.")
            return redirect('home')

        return _wrapped_view
    return decorator