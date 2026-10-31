"""
Pohledy pro kmenové zaměstnance Panther Security a samostatný archiv zaměstnanců
(ukončené pracovní poměry) včetně smluv a dokumentů o ukončení v PDF.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import role_required
from core.models import Employee, SystemRole
from core.forms import EmployeeArchiveForm
from core.services import (
    has_contract_template,
    has_termination_template,
    store_contract_pdf,
    store_termination_pdf,
)
from core.services.contract_pdf import NOTICE_PERIOD_DAYS


def _serve_employee_pdf(request, employee, file_field, label):
    """
    Vydá PDF uložené na kartě zaměstnance. Dokumenty obsahují rodné číslo,
    proto jdou jen přes pohledy s kontrolou role – ne přímým odkazem do /media/.
    """
    pdf = getattr(employee, file_field)
    if not pdf:
        messages.error(request, f"Zaměstnanec zatím nemá vygenerovaný dokument: {label}.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        pdf_file = pdf.open('rb')
    except FileNotFoundError:
        messages.error(request, f"Soubor ({label}) na serveru chybí. Vygenerujte ho znovu.")
        return redirect('employee_detail', employee_id=employee.id)

    filename = f"{label}_{employee.last_name}_{employee.first_name}.pdf".replace(' ', '_')
    return FileResponse(pdf_file, content_type='application/pdf', as_attachment=False, filename=filename)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_list_view(request):
    """Kmenový přehled aktivních zaměstnanců Panther Security."""
    employees = Employee.objects.filter(is_active=True, is_archived=False).select_related('department', 'position').order_by('last_name')
    return render(request, 'employees/employee_list.html', {'employees': employees})


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_detail_view(request, employee_id):
    """Karta zaměstnance s osobními údaji, smlouvou a historií směn."""
    employee = get_object_or_404(Employee, id=employee_id)
    shifts = employee.shifts.select_related('guard_object').order_by('-start_time')[:10]

    context = {
        'employee': employee,
        'shifts': shifts,
        'has_contract_template': has_contract_template(employee.contract_type),
        'has_termination_template': has_termination_template(employee.contract_type, employee.termination_type),
    }
    return render(request, 'employees/employee_detail.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_contract_view(request, employee_id):
    """Zobrazení smlouvy v PDF."""
    employee = get_object_or_404(Employee, id=employee_id)
    return _serve_employee_pdf(request, employee, 'contract_pdf', f"Smlouva {employee.contract_type}")


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_contract_regenerate_view(request, employee_id):
    """Nové vygenerování smlouvy (po opravě údajů nebo změně vzoru). Stará verze se nahradí."""
    employee = get_object_or_404(Employee, id=employee_id)
    if not has_contract_template(employee.contract_type):
        messages.error(request, f"Pro typ smlouvy {employee.get_contract_type_display()} zatím není připraven vzor.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        store_contract_pdf(employee)
        messages.success(request, f"Smlouva {employee.contract_type} pro {employee.full_name} byla vygenerována.")
    except Exception as e:
        messages.error(request, f"Smlouvu se nepodařilo vygenerovat: {e}")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_termination_view(request, employee_id):
    """Zobrazení dokumentu o ukončení (výpověď / dohoda o ukončení) v PDF."""
    employee = get_object_or_404(Employee, id=employee_id)
    label = employee.get_termination_type_display() or "Ukončení"
    return _serve_employee_pdf(request, employee, 'termination_pdf', label)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_termination_regenerate_view(request, employee_id):
    """Nové vygenerování dokumentu o ukončení z aktuálních údajů na kartě."""
    employee = get_object_or_404(Employee, id=employee_id, is_archived=True)
    if not has_termination_template(employee.contract_type, employee.termination_type):
        messages.error(request, "Pro tento typ smlouvy a způsob ukončení zatím není připraven vzor dokumentu.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        store_termination_pdf(employee)
        messages.success(request, f"Dokument „{employee.get_termination_type_display()}“ byl vygenerován.")
    except Exception as e:
        messages.error(request, f"Dokument o ukončení se nepodařilo vygenerovat: {e}")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_cssz_mark_view(request, employee_id):
    """
    Ruční potvrzení, že přihláška zaměstnance byla odeslána na ČSSZ (datovou schránkou).
    action=sent označí jako nahlášeno, action=undo označení zruší (omylem kliknuto).
    """
    employee = get_object_or_404(Employee, id=employee_id)
    action = request.POST.get('action')

    if action == 'sent':
        employee.is_reported_cssz = True
        employee.reported_cssz_date = timezone.now()
        messages.success(request, f"Přihláška {employee.full_name} na ČSSZ je označená jako odeslaná.")
    elif action == 'undo':
        employee.is_reported_cssz = False
        employee.reported_cssz_date = None
        messages.info(request, f"Označení odeslání na ČSSZ u {employee.full_name} bylo zrušeno.")
    else:
        messages.error(request, "Neznámá akce.")
        return redirect('employee_detail', employee_id=employee.id)

    employee.save(update_fields=['is_reported_cssz', 'reported_cssz_date'])
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def archive_employee_view(request, employee_id):
    """
    Ukončení pracovního poměru: uloží způsob a datum ukončení, vygeneruje výpověď / dohodu
    o ukončení v PDF a přesune zaměstnance do archivu.

    Stránka odesílá formulář přes fetch (hlavička X-Requested-With: fetch) a dostane JSON
    s adresou dokumentu, který otevře v novém okně. Bez JavaScriptu funguje běžné odeslání.
    """
    employee = get_object_or_404(Employee, id=employee_id, is_archived=False)
    form = EmployeeArchiveForm(request.POST or None, employee=employee)
    wants_json = request.headers.get('X-Requested-With') == 'fetch'

    if request.method == 'POST':
        if not form.is_valid():
            if wants_json:
                return JsonResponse({'ok': False}, status=400)
        else:
            employee.is_active = False
            employee.is_archived = True
            employee.termination_type = form.cleaned_data['termination_type']
            employee.termination_notice_date = form.cleaned_data['notice_date']
            employee.termination_date = form.cleaned_data['termination_date']
            employee.termination_reason = form.cleaned_data['termination_reason']
            if employee.user:
                employee.user.is_active = False
                employee.user.save(update_fields=['is_active'])
            employee.save()

            document_url = None
            if has_termination_template(employee.contract_type, employee.termination_type):
                try:
                    store_termination_pdf(employee)
                    document_url = reverse('employee_termination', args=[employee.id])
                except Exception as e:
                    messages.warning(request, f"Poměr byl ukončen, ale dokument se nepodařilo vygenerovat: {e}")

            messages.warning(
                request,
                f"Poměr zaměstnance {employee.full_name} končí dnem {employee.termination_date:%d.%m.%Y}. "
                f"Přesunut do archivu."
            )
            archive_url = reverse('employees_archive_list')
            if wants_json:
                return JsonResponse({'ok': True, 'redirect': archive_url, 'document': document_url})
            return redirect(archive_url)

    context = {
        'employee': employee,
        'form': form,
        'notice_days': NOTICE_PERIOD_DAYS.get(employee.contract_type),
        'has_templates': any(
            has_termination_template(employee.contract_type, key)
            for key, _ in Employee.TERMINATION_TYPE_CHOICES
        ),
    }
    return render(request, 'employees/employee_archive_confirm.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employees_archive_list_view(request):
    """Samostatný archiv propuštěných a neaktivních zaměstnanců."""
    archived = Employee.objects.filter(is_archived=True).order_by('-termination_date')
    return render(request, 'employees/employees_archive_list.html', {'archived_employees': archived})


@login_required
@role_required([SystemRole.OWNER])
def employee_delete_view(request, employee_id):
    """
    Kompletní a trvalé odstranění zaměstnance z databáze včetně jeho
    navázaného uživatelského účtu Django (User / auth_user), aby se v DB nehromadily sirotčí účty.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    user_to_delete = employee.user
    emp_name = getattr(employee, 'full_name', f"{employee.first_name} {employee.last_name}")

    if request.method == 'POST':
        # Soubory s osobními údaji se nesmažou samy s řádkem v DB
        for pdf in (employee.contract_pdf, employee.termination_pdf):
            if pdf:
                pdf.delete(save=False)
        # Smazáním employee se smaže profil
        employee.delete()
        # Následně smažeme i auth účet uživatele
        if user_to_delete:
            user_to_delete.delete()

        messages.success(request, f"Zaměstnanec {emp_name} i jeho uživatelský účet byli trvale odstraněni.")
        return redirect('employee_list')

    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})