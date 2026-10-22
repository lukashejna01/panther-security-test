"""
Pohledy pro kmenové zaměstnance Panther Security a samostatný archiv zaměstnanců
(ukončené pracovní poměry).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import role_required
from core.models import Employee, SystemRole
from core.forms import EmployeeArchiveForm


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
    }
    return render(request, 'employees/employee_detail.html', context)


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
        # Smazáním employee se smaže profil
        employee.delete()
        # Následně smažeme i auth účet uživatele
        if user_to_delete:
            user_to_delete.delete()

        messages.success(request, f"Zaměstnanec {emp_name} i jeho uživatelský účet byli trvale odstraněni.")
        return redirect('employee_list')

    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})