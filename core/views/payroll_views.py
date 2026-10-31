"""
Mzdový modul Panther Security:
- Měsíční sumář mzdových nákladů ze schválených směn s roletkami pro manažera a majitele.
- Automatický výpočet mezd, čisté výplaty a zákonných odvodů (SP, ZP, daň) pro rok 2026.
- Detailní výplatní páska pro zaměstnance i vedení (ze směn i manuální).
- Odečet záloh v reálném výplatním cyklu (od 25. dne odpracovaného měsíce do 24. dne výplatního měsíce).
"""

from decimal import Decimal
from datetime import datetime, date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Sum

from core.decorators import role_required
from core.models import Employee, Shift, ShiftStatus, SystemRole, AdvancePayment

# Nastavený výplatní den v měsíci
PAYROLL_PAYOUT_DAY = 25


def get_advance_period_for_payroll(payroll_year: int, payroll_month: int, payout_day: int = PAYROLL_PAYOUT_DAY):
    """
    Vrátí časové rozmezí záloh (start, end) pro danou mzdu.
    Např. pro mzdu za říjen (10) při výplatě 25. listopadu (11):
    start = 25. 10. v 00:00:00
    end   = 24. 11. ve 23:59:59
    """
    if payroll_month == 12:
        next_year = payroll_year + 1
        next_month = 1
    else:
        next_year = payroll_year
        next_month = payroll_month + 1

    start_dt = datetime(payroll_year, payroll_month, payout_day, 0, 0, 0)
    end_dt = datetime(next_year, next_month, payout_day - 1, 23, 59, 59)

    return timezone.make_aware(start_dt), timezone.make_aware(end_dt)


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
    """Měsíční sumář mzdových nákladů s odečtem záloh za daný výplatní cyklus."""
    now = timezone.now()

    year_val = request.GET.get('year')
    month_val = request.GET.get('month')
    year = int(year_val) if year_val and year_val.isdigit() else now.year
    month = int(month_val) if month_val and month_val.isdigit() else now.month

    # Výpočet intervalu pro zálohy (od 25. dne do 24. dne dalšího měsíce)
    adv_start, adv_end = get_advance_period_for_payroll(year, month)

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
    grand_advances = 0.0
    grand_payout = 0.0
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

        # Načtení záloh z výplatního období (25. odpracovaného měsíce až 24. výplatního měsíce)
        advances_sum = AdvancePayment.objects.filter(
            employee=emp,
            status__in=['ISSUED', 'SETTLED'],
            created_at__gte=adv_start,
            created_at__lte=adv_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        if hours > 0 or advances_sum > 0:
            calc = calculate_czech_payroll_2026(pay, emp.contract_type)
            adv_float = float(advances_sum)
            net_payout = max(0.0, round(calc['net'] - adv_float, 2))

            payroll_data.append({
                'employee': emp,
                'contract_type': emp.contract_type or 'DPP',
                'shifts_count': shifts.count(),
                'hours': round(hours, 1),
                'hourly_rate': emp.hourly_rate,
                'calc': calc,
                'advances_total': advances_sum,
                'net_payout': net_payout,
            })

            grand_hours += hours
            grand_gross += calc['gross']
            grand_net += calc['net']
            grand_advances += adv_float
            grand_payout += net_payout
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
        'advance_period_start': adv_start,
        'advance_period_end': adv_end,
        'grand_hours': round(grand_hours, 1),
        'grand_gross': round(grand_gross, 2),
        'grand_net': round(grand_net, 2),
        'grand_advances': round(grand_advances, 2),
        'grand_payout': round(grand_payout, 2),
        'grand_emp_sp': round(grand_emp_sp, 2),
        'grand_emp_zp': round(grand_emp_zp, 2),
        'grand_emp_tax': round(grand_emp_tax, 2),
        'grand_comp_costs': round(grand_comp_costs, 2),
    }
    return render(request, 'payroll/payroll_summary.html', context)


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def payslip_detail_view(request, employee_id, year, month):
    """Zobrazení a tisk výplatní pásky s odečtem záloh z intervalu výplatního cyklu."""
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

    # Načtení záloh za reálný výplatní cyklus (25. den měsíce M až 24. den měsíce M+1)
    adv_start, adv_end = get_advance_period_for_payroll(year, month)
    emp_advances = AdvancePayment.objects.filter(
        employee=target_employee,
        status__in=['ISSUED', 'SETTLED'],
        created_at__gte=adv_start,
        created_at__lte=adv_end
    ).order_by('created_at')

    total_advances = sum(a.amount for a in emp_advances)
    net_payout = max(Decimal('0.00'), Decimal(str(calc['net'])) - total_advances)

    context = {
        'employee': target_employee,
        'year': year,
        'month': month,
        'advance_period_start': adv_start,
        'advance_period_end': adv_end,
        'approved_shifts': approved_shifts,
        'advances': emp_advances,
        'total_advances': total_advances,
        'net_payout': net_payout,
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
    """Generování jednorázové výplatní pásky pro kohokoli."""
    now = timezone.now()
    employees = Employee.objects.filter(is_active=True).order_by('last_name')

    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        month = int(request.POST.get('month', now.month))
        year = int(request.POST.get('year', now.year))

        adv_start, adv_end = get_advance_period_for_payroll(year, month)
        advances_sum = Decimal('0.00')
        emp_advances = []

        if employee_id:
            emp = get_object_or_404(Employee, id=employee_id)
            full_name = emp.full_name
            personal_number = emp.personal_number
            contract_type = request.POST.get('contract_type') or emp.contract_type or 'DPP'
            bank_account = request.POST.get('bank_account') or emp.bank_account or 'Výplata v hotovosti'
            health_code = emp.get_health_insurance_code_display() if hasattr(emp, 'get_health_insurance_code_display') else ''
            
            emp_advances = list(AdvancePayment.objects.filter(
                employee=emp,
                status__in=['ISSUED', 'SETTLED'],
                created_at__gte=adv_start,
                created_at__lte=adv_end
            ).order_by('created_at'))
            advances_sum = sum(a.amount for a in emp_advances)
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
        net_payout = max(Decimal('0.00'), Decimal(str(calc['net'])) - advances_sum)

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
            'advance_period_start': adv_start,
            'advance_period_end': adv_end,
            'advances': emp_advances,
            'total_hours': round(hours, 1),
            'gross_pay': calc['gross'],
            'emp_sp': calc['emp_sp'],
            'emp_zp': calc['emp_zp'],
            'tax': calc['emp_tax'],
            'comp_sp': calc['comp_sp'],
            'comp_zp': calc['comp_zp'],
            'comp_total_insurance': calc['comp_total_insurance'],
            'net_pay': calc['net'],
            'total_advances': advances_sum,
            'net_payout': net_payout,
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