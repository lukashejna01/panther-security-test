"""
Předvyplnění odhlášky z ČSSZ (REGZEC akce 2) z dat aplikace.

Podklady pro úřad práce (průměrný čistý výdělek, doby důchodového pojištění) se
odhadují ze schválených směn a mzdového výpočtu aplikace. Jsou to návrhy – před
odesláním je musí zkontrolovat ten, kdo vede mzdy.
"""

import math
from collections import defaultdict
from datetime import date, timedelta

# Způsob ukončení v aplikaci → důvod ukončení PPV (číselník C_DUVUKPRACVZT)
REASON_BY_TERMINATION_TYPE = {
    'AGREEMENT': '2',        # dohodou (§ 49 ZP)
    'EMPLOYEE_NOTICE': '3',  # výpověď zaměstnance (§ 50 ZP)
}


def _month_start(d):
    return d.replace(day=1)


def _month_end(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    return date(year, month % 12 + 1, 1)


def monthly_gross(employee):
    """Hrubý výdělek po měsících ze schválených směn: {date(rok, měsíc, 1): Kč}."""
    from django.utils import timezone
    from core.models import Shift, ShiftStatus

    totals = defaultdict(float)
    shifts = Shift.objects.filter(employee=employee, status=ShiftStatus.APPROVED)
    for shift in shifts:
        month = _month_start(timezone.localtime(shift.start_time).date())
        totals[month] += shift.total_cost
    return dict(totals)


def insured_months(employee, gross_by_month):
    """
    Měsíce s účastí na důchodovém pojištění. HPP po celou dobu zaměstnání,
    DPP a DPČ jen v měsících, kdy výdělek dosáhl rozhodného příjmu (stejná hranice
    jako ve výpočtu mezd aplikace).
    """
    from core.views.payroll_views import calculate_czech_payroll_2026

    start, end = employee.start_employment_date, employee.termination_date
    if not start or not end:
        return []
    months = []
    month = _month_start(start)
    while month <= end:
        gross = gross_by_month.get(month, 0.0)
        if employee.contract_type == 'HPP':
            months.append(month)
        elif gross > 0 and not calculate_czech_payroll_2026(gross, employee.contract_type)['is_exempt']:
            months.append(month)
        month = _add_months(month, 1)
    return months


def pension_periods(employee, months):
    """
    Souvislá období pojištění za posledních 24 měsíců před skončením
    (oříznutá na den nástupu a skončení). Když v těch 24 měsících nic není,
    uvede se pojištění z tohoto zaměstnání i starší.
    """
    start, end = employee.start_employment_date, employee.termination_date
    window_start = _add_months(_month_start(end), -23)
    recent = [m for m in months if m >= window_start] or months

    periods = []
    for month in recent:
        if periods and periods[-1][1] == _add_months(month, -1):
            periods[-1][1] = month
        else:
            periods.append([month, month])
    return [(max(first, start), min(_month_end(last), end)) for first, last in periods]


def average_net_earnings(employee, gross_by_month):
    """
    Odhad průměrného měsíčního čistého výdělku: rozhodné období je předchozí
    kalendářní čtvrtletí. Když v něm zaměstnanec nepracoval, vezme se pravděpodobný
    výdělek z měsíců, které odpracoval. Zaokrouhluje se na celé koruny nahoru.
    """
    from core.services.tax import monthly_credits
    from core.views.payroll_views import calculate_czech_payroll_2026

    end = employee.termination_date
    quarter_start = date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
    previous_quarter = [_add_months(quarter_start, -3 + i) for i in range(3)]

    months = [m for m in previous_quarter if gross_by_month.get(m)]
    if not months:
        months = [m for m, gross in gross_by_month.items() if gross and m <= end]
    if not months:
        return None
    net = 0.0
    for m in months:
        # Se slevami podle prohlášení, ale bez daňového bonusu (ten se nepřičítá)
        calc = calculate_czech_payroll_2026(gross_by_month[m], employee.contract_type,
                                            credits=monthly_credits(employee, m.year, m.month))
        net += calc['net'] - calc['tax_bonus']
    return math.ceil(net / len(months))


def deregistration_suggestions(employee):
    """Návrh údajů do formuláře odhlášky."""
    suggestion = {
        'ikmpsv': employee.cssz_ikmpsv,
        'job_id': employee.cssz_job_id,
        'reason': REASON_BY_TERMINATION_TYPE.get(employee.termination_type, ''),
        'no_insurance': False,
        'avg_net': None,
        'periods': [],
    }
    end = employee.termination_date
    if not end or not employee.start_employment_date:
        return suggestion

    # Smlouva na dobu určitou skončila v den, na který byla sjednaná
    if not suggestion['reason'] and employee.contract_end_date == end:
        suggestion['reason'] = '12'

    gross = monthly_gross(employee)
    months = insured_months(employee, gross)
    if not months:
        # Např. DPP pod limitem – zaměstnání nezaložilo účast na pojištění.
        # U zaměstnanců z doby před aplikací ale mzdy v aplikaci prostě nejsou, to nic neříká.
        suggestion['no_insurance'] = not employee.cssz_registered_before_app
        return suggestion

    suggestion['periods'] = pension_periods(employee, months)
    suggestion['avg_net'] = average_net_earnings(employee, gross)
    return suggestion
