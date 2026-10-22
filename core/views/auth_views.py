"""
Pohledy pro přihlašování, odhlašování, rozcestník podle rolí a správu hesel.
"""

import secrets
import string
import unicodedata
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from core.models import SystemRole
from core.forms import EmployeeProfileUpdateForm


def remove_accents(input_str: str) -> str:
    """Odstraní diakritiku a převede text na malá písmena pro username."""
    if not input_str:
        return ""
    nfkd = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()


def generate_credentials(first_name: str, last_name: str):
    """Vygeneruje unikátní přihlašovací jméno (jmeno.prijmeni) a náhodné silné heslo."""
    clean_fn = remove_accents(first_name).strip()
    clean_ln = remove_accents(last_name).strip()
    base_username = f"{clean_fn}.{clean_ln}" if clean_fn and clean_ln else "strazny"

    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for _ in range(10))
    return username, password


def redirect_user_by_role(user):
    """Automatické přesměrování do správného portálu podle role."""
    if user.is_superuser:
        return redirect('owner_dashboard')

    profile = getattr(user, 'employee_profile', None)
    if profile:
        if profile.system_role == SystemRole.OWNER:
            return redirect('owner_dashboard')
        elif profile.system_role == SystemRole.MANAGER:
            return redirect('manager_dashboard')
        else:
            return redirect('employee_portal')

    return redirect('employee_portal')


def home_view(request):
    """Veřejný rozcestník Panther Security."""
    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)
    return render(request, 'auth/home.html')


def login_view(request):
    """Přihlášení uživatele s přesměrováním do příslušného portálu."""
    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect_user_by_role(user)
        else:
            messages.error(request, "Neplatné uživatelské jméno nebo heslo.")

    return render(request, 'auth/login.html')


def logout_view(request):
    """Odhlášení uživatele."""
    logout(request)
    messages.info(request, "Byl jste úspěšně odhlášen.")
    return redirect('login')


@login_required
def profile_view(request):
    """Zobrazení a editace kontaktů zaměstnance a změna hesla."""
    profile = getattr(request.user, 'employee_profile', None)
    profile_form = EmployeeProfileUpdateForm(instance=profile) if profile else None
    password_form = PasswordChangeForm(user=request.user)

    if request.method == 'POST':
        if 'update_profile' in request.POST and profile:
            profile_form = EmployeeProfileUpdateForm(request.POST, instance=profile)
            if profile_form.is_valid():
                profile_form.save()
                if profile.email and request.user.email != profile.email:
                    request.user.email = profile.email
                    request.user.save(update_fields=['email'])
                messages.success(request, "Kontaktní a bankovní údaje byly úspěšně uloženy.")
                return redirect('user_profile')
            else:
                messages.error(request, "Zkontrolujte zadané kontaktní údaje.")

        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Vaše heslo bylo úspěšně změněno.")
                return redirect('user_profile')
            else:
                messages.error(request, "Chyba při změně hesla. Zkontrolujte stávající i nové heslo.")

    context = {
        'profile': profile,
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'employees/employee_profile.html', context)