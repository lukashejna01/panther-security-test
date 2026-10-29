"""
Mzdový modul Panther Security:
- Měsíční sumář mzdových nákladů s roletkami pro manažera a majitele.
- Automatický výpočet mezd, čisté výplaty a zákonných odvodů (SP, ZP, daň) pro rok 2026.
- Detailní výplatní páska pro zaměstnance i vedení (ze směn i manuální).
"""

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.models import Employee, Shift, ShiftStatus, SystemRole


def calculate_czech_payroll_2026(gross_amount: float, contract_type: str, has_tax_declaration: bool = False):
    """
    Kalkulátor odvodů a čisté mzdy podle legislativy pro rok 2026:
    - DPP: limit 12 000 Kč.
    - DPČ: limit 4 500 Kč.
    - HPP: plné odvody (SP 7.1 % + 24.8 %, ZP 4.5 % + 9.0 %).
    - IČO: fakturace bez srážek, čistá = hrubá.
    - Daň z příjmu: 15 %.
    """
    gross = round(float(gross_amount or 0.0), 2)
    contract = (contract_type or '').upper()

    emp_sp = 0.0
    emp_zp = 0.0
    comp_sp = 0.0
    comp_zp = 0.0

    if 'ICO' in contract or 'IČO' in contract or 'OSVC' in contract or 'OSVČ' in contract:
        return {
            'gross': gross,
            'emp_sp': 0.0,
            'emp_zp': 0.0,
            'emp_tax': 0.0,
            'comp_sp': 0.0,
            'comp_zp': 0.0,
            'comp_total_insurance': 0.0,
            'net': gross,
            'total_cost': gross,
            'is_exempt': True,
        }

    elif 'DPP' in contract:
        if gross < 12000:
            is_exempt = True
        else:
            is_exempt = False
            emp_sp = round(gross * 0.071, 2)
            emp_zp = round(gross * 0.045, 2)
            comp_sp = round(gross * 0.248, 2)
            comp_zp = round(gross * 0.090, 2)

    elif 'DPČ' in contract or 'DPC' in contract:
        if gross < 4500:
            is_exempt = True
        else:
            is_exempt = False
            emp_sp = round(gross * 0.071, 2)
            emp_zp = round(gross * 0.045, 2)
            comp_sp = round(gross * 0.248, 2)
            comp_zp = round(gross * 0.090, 2)

    else:
        is_exempt = False
        emp_sp = round(gross * 0.071, 2)
        emp_zp = round(gross * 0.045, 2)
        comp_sp = round(gross * 0.248, 2)
        comp_zp = round(gross * 0.090, 2)

    calculated_tax = round(gross * 0.15, 2)
    if has_tax_declaration:
        tax_credit = 2570.00
        emp_tax = max(0.0, round(calculated_tax - tax_credit, 2))
    else:
        emp_tax = calculated_tax

    net = max(0.0, round(gross - emp_sp - emp_zp - emp_tax, 2))
    total_cost = round(gross + comp_sp + comp_zp, 2)

    return {
        'gross': gross,
        'emp_sp': emp_sp,
        'emp_zp': emp_zp,
        'emp_tax': emp_tax,
        'comp_sp': comp_sp,
        'comp_zp': comp_zp,
        'comp_total_insurance': round(comp_sp + comp_zp, 2),
        'net': net,
        'total_cost': total_cost,
        'is_exempt': is_exempt,
    }


@login_required
@role_required([SystemRole.OWNER, SystemRole.MANAGER])
def payroll_summary_view(request):
    """Měsíční sumář mzdových nákladů ze schválených směn s roletkami měsíc/rok a odvody 2026."""
    now = timezone.now()

    year_val = request.GET.get('year')
    month_val = request.GET.get('month')
    year = int(year_val) if year_val and year_val.isdigit() else now.year
    month = int(month_val) if month_val and month_val.isdigit() else now.month

    months_list = [
        (1, 'Leden'), (2, 'Únor'), (3, 'Březen'), (4, 'Duben'),
        (5, 'Květen'), (6, 'Červen'), (7, 'Červenec'), (8, 'Srpen'),
        (9, 'Září'), (10, 'Říjen'), (11, 'Listopad'), (12, 'Prosinec')
    ]
    available_years = list(range(now.year - 2, now.year + 3))

    employees = Employee.objects.filter(is_active=True).order_by('last_name')
    payroll_data = []

    grand_hours = 0.0
    grand_gross = 0.0
    grand_net = 0.0
    grand_emp_sp = 0.0
    grand_emp_zp = 0.0
    grand_emp_tax = 0.0
    grand_comp_costs = 0.0

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
            calc = calculate_czech_payroll_2026(pay, emp.contract_type)
            payroll_data.append({
                'employee': emp,
                'contract_type': emp.contract_type or 'DPP',
                'shifts_count': shifts.count(),
                'hours': round(hours, 1),
                'hourly_rate': emp.hourly_rate,
                'calc': calc,
            })

            grand_hours += hours
            grand_gross += calc['gross']
            grand_net += calc['net']
            grand_emp_sp += calc['emp_sp']
            grand_emp_zp += calc['emp_zp']
            grand_emp_tax += calc['emp_tax']
            grand_comp_costs += calc['total_cost']

    context = {
        'year': year,
        'month': month,
        'months_list': months_list,
        'available_years': available_years,
        'payroll_data': payroll_data,
        'grand_hours': round(grand_hours, 1),
        'grand_gross': round(grand_gross, 2),
        'grand_net': round(grand_net, 2),
        'grand_emp_sp': round(grand_emp_sp, 2),
        'grand_emp_zp': round(grand_emp_zp, 2),
        'grand_emp_tax': round(grand_emp_tax, 2),
        'grand_comp_costs': round(grand_comp_costs, 2),
    }
    return render(request, 'payroll/payroll_summary.html', context)


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def payslip_detail_view(request, employee_id, year, month):
    """Zobrazení a tisk výplatní pásky zaměstnance se zákonnými odvody 2026."""
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

    calc = calculate_czech_payroll_2026(gross_pay, target_employee.contract_type)

    context = {
        'employee': target_employee,
        'year': year,
        'month': month,
        'approved_shifts': approved_shifts,
        'total_hours': round(total_hours, 1),
        'gross_pay': calc['gross'],
        'emp_sp': calc['emp_sp'],
        'emp_zp': calc['emp_zp'],
        'tax': calc['emp_tax'],
        'comp_sp': calc['comp_sp'],
        'comp_zp': calc['comp_zp'],
        'comp_total_insurance': calc['comp_total_insurance'],
        'net_pay': calc['net'],
        'total_company_cost': calc['total_cost'],
        'is_exempt': calc['is_exempt'],
    }
    return render(request, 'payroll/payslip_detail.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def payslip_custom_generate_view(request):
    """Generování jednorázové výplatní pásky pro kohokoli (ze seznamu i ručně zadaného)."""
    now = timezone.now()
    employees = Employee.objects.filter(is_active=True).order_by('last_name')

    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        month = int(request.POST.get('month', now.month))
        year = int(request.POST.get('year', now.year))

        if employee_id:
            emp = get_object_or_404(Employee, id=employee_id)
            full_name = emp.full_name
            personal_number = emp.personal_number
            contract_type = request.POST.get('contract_type') or emp.contract_type or 'DPP'
            bank_account = request.POST.get('bank_account') or emp.bank_account or 'Výplata v hotovosti'
            health_code = emp.get_health_insurance_code_display() if hasattr(emp, 'get_health_insurance_code_display') else ''
        else:
            full_name = request.POST.get('manual_name', '').strip() or 'Externí pracovník'
            personal_number = request.POST.get('manual_personal_number', '').strip()
            contract_type = request.POST.get('contract_type', 'DPP')
            bank_account = request.POST.get('bank_account', '').strip() or 'Výplata v hotovosti'
            health_code = request.POST.get('health_insurance', '').strip()

        hours = float(request.POST.get('hours', 0.0) or 0.0)
        hourly_rate = float(request.POST.get('hourly_rate', 0.0) or 0.0)
        custom_gross = request.POST.get('gross_pay')

        if custom_gross:
            gross_pay = float(custom_gross)
            if hours > 0 and hourly_rate == 0:
                hourly_rate = round(gross_pay / hours, 2)
        else:
            gross_pay = round(hours * hourly_rate, 2)

        calc = calculate_czech_payroll_2026(gross_pay, contract_type)

        mock_employee = {
            'full_name': full_name,
            'personal_number': personal_number,
            'contract_type': contract_type,
            'bank_account': bank_account,
            'hourly_rate': hourly_rate,
            'get_health_insurance_code_display': health_code,
        }

        context = {
            'employee': mock_employee,
            'year': year,
            'month': month,
            'total_hours': round(hours, 1),
            'gross_pay': calc['gross'],
            'emp_sp': calc['emp_sp'],
            'emp_zp': calc['emp_zp'],
            'tax': calc['emp_tax'],
            'comp_sp': calc['comp_sp'],
            'comp_zp': calc['comp_zp'],
            'comp_total_insurance': calc['comp_total_insurance'],
            'net_pay': calc['net'],
            'total_company_cost': calc['total_cost'],
            'is_exempt': calc['is_exempt'],
        }
        return render(request, 'payroll/payslip_detail.html', context)

    months_list = [
        (1, 'Leden'), (2, 'Únor'), (3, 'Březen'), (4, 'Duben'),
        (5, 'Květen'), (6, 'Červen'), (7, 'Červenec'), (8, 'Srpen'),
        (9, 'Září'), (10, 'Říjen'), (11, 'Listopad'), (12, 'Prosinec')
    ]
    available_years = list(range(now.year - 2, now.year + 3))

    context = {
        'employees': employees,
        'months_list': months_list,
        'available_years': available_years,
        'current_month': now.month,
        'current_year': now.year,
    }
    return render(request, 'payroll/payslip_custom_form.html', context)