"""
Pohledy pro kmenové zaměstnance Panther Security a samostatný archiv zaměstnanců
(ukončené pracovní poměry).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.decorators import role_required
from core.models import Employee, SystemRole
from core.forms import EmployeeArchiveForm
from core.services import has_contract_template, store_contract_pdf


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
    }
    return render(request, 'employees/employee_detail.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_contract_view(request, employee_id):
    """
    Zobrazení smlouvy v PDF. Soubor obsahuje rodné číslo, proto se vydává
    jen přes tento pohled s kontrolou role – ne přímým odkazem do /media/.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    if not employee.contract_pdf:
        messages.error(request, "Zaměstnanec zatím nemá vygenerovanou smlouvu.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        pdf_file = employee.contract_pdf.open('rb')
    except FileNotFoundError:
        messages.error(request, "Soubor smlouvy na serveru chybí. Vygenerujte ji znovu.")
        return redirect('employee_detail', employee_id=employee.id)

    filename = f"{employee.contract_type}_{employee.last_name}_{employee.first_name}.pdf"
    return FileResponse(pdf_file, content_type='application/pdf', as_attachment=False, filename=filename)


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
def archive_employee_view(request, employee_id):
    """Ukončení pracovního poměru a přesun zaměstnance do archivu."""
    employee = get_object_or_404(Employee, id=employee_id, is_archived=False)
    form = EmployeeArchiveForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        employee.is_active = False
        employee.is_archived = True
        employee.termination_date = form.cleaned_data['termination_date']
        employee.termination_reason = form.cleaned_data['termination_reason']
        if employee.user:
            employee.user.is_active = False
            employee.user.save(update_fields=['is_active'])
        employee.save()
        messages.warning(request, f"Pracovní poměr zaměstnance {employee.full_name} byl ukončen. Přesunut do archivu.")
        return redirect('employee_list')

    return render(request, 'employees/employee_archive_confirm.html', {'employee': employee, 'form': form})


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
        # Soubor smlouvy s osobními údaji se nesmaže sám s řádkem v DB
        if employee.contract_pdf:
            employee.contract_pdf.delete(save=False)
        # Smazáním employee se smaže profil
        employee.delete()
        # Následně smažeme i auth účet uživatele
        if user_to_delete:
            user_to_delete.delete()

        messages.success(request, f"Zaměstnanec {emp_name} i jeho uživatelský účet byli trvale odstraněni.")
        return redirect('employee_list')

    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})