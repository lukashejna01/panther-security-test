"""
Mzdový modul Panther Security:
- Měsíční sumář mzdových nákladů s roletkami pro manažera a majitele.
- Automatický výpočet mezd, čisté výplaty a zákonných odvodů (SP, ZP, daň) pro rok 2026.
- Detailní výplatní páska pro zaměstnance i vedení.
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
    - DPP: limit účasti na pojištění 12 000 Kč (do 11 999 Kč bez SP a ZP).
    - DPČ: limit účasti na pojištění 4 500 Kč (do 4 499 Kč bez SP a ZP).
    - HPP: plné odvody (SP 7.1 % + 24.8 %, ZP 4.5 % + 9.0 %).
    - IČO: fakturace bez srážek, čistá = hrubá.
    - Daň z příjmu: 15 % (při podepsaném prohlášení sleva na poplatníka až 2 570 Kč měsíčně).
    """
    gross = round(float(gross_amount or 0.0), 2)
    contract = (contract_type or '').upper()

    emp_sp = 0.0
    emp_zp = 0.0
    comp_sp = 0.0
    comp_zp = 0.0

    # 1. Živnostník (IČO / OSVČ)
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
            'limit_text': 'IČO (fakturace bez srážek)',
        }

    # 2. DPP (Dohoda o provedení práce) – limit 2026 je 12 000 Kč
    elif 'DPP' in contract:
        if gross < 12000:
            is_exempt = True
            limit_text = 'Do limitu 12 000 Kč (bez odvodů SP/ZP)'
        else:
            is_exempt = False
            limit_text = 'Od 12 000 Kč (plné odvody SP/ZP)'
            emp_sp = round(gross * 0.071, 2)
            emp_zp = round(gross * 0.045, 2)
            comp_sp = round(gross * 0.248, 2)
            comp_zp = round(gross * 0.090, 2)

    # 3. DPČ (Dohoda o pracovní činnosti) – limit 2026 je 4 500 Kč
    elif 'DPČ' in contract or 'DPC' in contract:
        if gross < 4500:
            is_exempt = True
            limit_text = 'Do limitu 4 500 Kč (bez odvodů SP/ZP)'
        else:
            is_exempt = False
            limit_text = 'Od 4 500 Kč (plné odvody SP/ZP)'
            emp_sp = round(gross * 0.071, 2)
            emp_zp = round(gross * 0.045, 2)
            comp_sp = round(gross * 0.248, 2)
            comp_zp = round(gross * 0.090, 2)

    # 4. HPP (Hlavní pracovní poměr)
    else:
        is_exempt = False
        limit_text = 'HPP (standardní pracovní poměr)'
        emp_sp = round(gross * 0.071, 2)
        emp_zp = round(gross * 0.045, 2)
        comp_sp = round(gross * 0.248, 2)
        comp_zp = round(gross * 0.090, 2)

    # Daň z příjmu 15 %
    calculated_tax = round(gross * 0.15, 2)
    if has_tax_declaration:
        # Měsíční sleva na poplatníka v roce 2026: 2 570 Kč (30 840 Kč ročně)
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
        'limit_text': limit_text,
    }


@login_required
@role_required(SystemRole.OWNER)
def payroll_summary_view(request):
    """Měsíční sumář mzdových nákladů ze schválených směn s roletkami měsíc/rok a odvody 2026."""
    now = timezone.now()

    year_val = request.GET.get('year')
    month_val = request.GET.get('month')
    year = int(year_val) if year_val and year_val.isdigit() else now.year
    month = int(month_val) if month_val and month_val.isdigit() else now.month

    # Seznamy pro roletky
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

    # Bezpečnost: Řadový strážný smí vidět pouze svou pásku
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

    # Výpočet odvodů a čisté mzdy podle legislativy 2026
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
        'limit_text': calc['limit_text'],
    }
    return render(request, 'payroll/payslip_detail.html', context)