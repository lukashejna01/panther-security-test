"""
Mzdový modul: celkový měsíční sumář pro manažera/majitele a detail výplatní pásky.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.models import Employee, Shift, ShiftStatus, SystemRole


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def payroll_summary_view(request):
    """Měsíční sumář mzdových nákladů ze schválených směn."""
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    employees = Employee.objects.filter(is_active=True).order_by('last_name')
    payroll_data = []
    grand_pay = 0.0
    grand_hours = 0.0

    for emp in employees:
        shifts = Shift.objects.filter(
            employee=emp,
            status=ShiftStatus.APPROVED,
            start_time__year=year,
            start_time__month=month
        )
        hours = sum(float(s.planned_hours) for s in shifts)
        pay = sum(float(s.total_cost) for s in shifts)

        if hours > 0:
            payroll_data.append({
                'employee': emp,
                'hours': round(hours, 1),
                'total_pay': round(pay, 2),
                'shifts_count': shifts.count(),
            })
            grand_pay += pay
            grand_hours += hours

    context = {
        'year': year,
        'month': month,
        'payroll_data': payroll_data,
        'grand_pay': round(grand_pay, 2),
        'grand_hours': round(grand_hours, 1),
    }
    return render(request, 'payroll/payroll_summary.html', context)


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def payslip_detail_view(request, employee_id, year, month):
    """Zobrazení a tisk výplatní pásky zaměstnance."""
    profile = getattr(request.user, 'employee_profile', None)
    target_employee = get_object_or_404(Employee, id=employee_id)

    if profile and profile.system_role == SystemRole.STAFF and profile.id != target_employee.id:
        messages.error(request, "Nemáte oprávnění prohlížet cizí výplatní pásku.")
        return redirect('employee_portal')

    approved_shifts = Shift.objects.filter(
        employee=target_employee,
        status=ShiftStatus.APPROVED,
        start_time__year=year,
        start_time__month=month
    ).select_related('guard_object').order_by('start_time')

    total_hours = sum(float(s.planned_hours) for s in approved_shifts)
    gross_pay = sum(float(s.total_cost) for s in approved_shifts)

    tax_rate = 0.15 if gross_pay > 10000 else 0.0
    tax = round(gross_pay * tax_rate, 2)
    net_pay = round(gross_pay - tax, 2)

    context = {
        'employee': target_employee,
        'year': year,
        'month': month,
        'approved_shifts': approved_shifts,
        'total_hours': round(total_hours, 1),
        'gross_pay': round(gross_pay, 2),
        'tax': tax,
        'net_pay': net_pay,
    }
    return render(request, 'payroll/payslip_detail.html', context)