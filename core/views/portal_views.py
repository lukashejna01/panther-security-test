"""
Hlavní portály:
- Portál strážného (plánované směny, probíhající služba, čekající na schválení, schválené do mzdy)
- Dispečink manažera (čekající směny ke schválení, přehled stanovišť)
- Kokpit majitele (ziskovost, ekonomika, marže)
"""

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from core.decorators import role_required
from core.models import Candidate, GuardObject, Invoice, InvoiceType, Shift, ShiftStatus, SystemRole


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def employee_portal_view(request):
    """
    Portál zaměstnance se 4 jasnými sekcemi:
    1. Právě probíhající směna (pokud slouží teď)
    2. Plánované budoucí směny
    3. Odsloužené směny čekající na schválení manažerem
    4. Schválené směny (připsané do měsíční mzdy)
    """
    profile = getattr(request.user, 'employee_profile', None)
    now = timezone.now()

    in_progress_shift = None
    upcoming_shifts = []
    pending_shifts = []
    approved_shifts = []
    month_earned = 0.0
    month_hours = 0.0

    if profile:
        # 1. Probíhající směna
        in_progress_shift = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.IN_PROGRESS
        ).first()

        # 2. Plánované budoucí směny
        upcoming_shifts = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.ASSIGNED,
            start_time__gte=now
        ).select_related('guard_object').order_by('start_time')

        # 3. Odslouženo - čeká na schválení
        pending_shifts = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.COMPLETED
        ).select_related('guard_object').order_by('-end_time')

        # 4. Schváleno v aktuálním měsíci (připsáno do mzdy)
        first_day_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        approved_shifts = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.APPROVED,
            start_time__gte=first_day_month
        ).select_related('guard_object').order_by('-start_time')

        for s in approved_shifts:
            month_hours += float(s.planned_hours)
            month_earned += float(s.total_cost)

    # Volné směny z burzy
    open_shifts = Shift.objects.filter(
        status=ShiftStatus.OPEN,
        start_time__gte=now
    ).exclude(employee=profile).select_related('guard_object').order_by('start_time')

    context = {
        'profile': profile,
        'in_progress_shift': in_progress_shift,
        'upcoming_shifts': upcoming_shifts,
        'pending_shifts': pending_shifts,
        'approved_shifts': approved_shifts,
        'open_shifts': open_shifts,
        'month_hours': round(month_hours, 1),
        'month_earned': round(month_earned, 2),
    }
    return render(request, 'portals/portal_employee.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def manager_dashboard_view(request):
    """
    Dispečerský portál manažera:
    - Směny čekající na schválení po skončení služby (schválení do mezd)
    - Dnešní operativní stav stanovišť
    - Rychlý náhled náborové pipeline
    """
    now = timezone.now()

    # Směny ke schválení (skončily a čekají na podpis manažera)
    shifts_to_approve = Shift.objects.filter(
        status=ShiftStatus.COMPLETED
    ).select_related('guard_object', 'employee').order_by('-end_time')

    # Dnes ve službě
    active_now = Shift.objects.filter(status=ShiftStatus.IN_PROGRESS).select_related('guard_object', 'employee')
    open_market = Shift.objects.filter(status=ShiftStatus.OPEN, start_time__gte=now).count()
    active_candidates_count = Candidate.objects.filter(is_archived=False).count()

    context = {
        'shifts_to_approve': shifts_to_approve,
        'active_now': active_now,
        'open_market_count': open_market,
        'active_candidates_count': active_candidates_count,
    }
    return render(request, 'portals/portal_manager.html', context)


@login_required
@role_required([SystemRole.OWNER])
def owner_dashboard_view(request):
    """
    Ekonomický kokpit majitele:
    - Finanční bilance (vydané tržby vs. dodavatelé vs. schválené mzdy)
    - Ziskovost jednotlivých střežených objektů
    """
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    outgoing = Invoice.objects.filter(invoice_type=InvoiceType.OUTGOING, issue_date__year=year, issue_date__month=month)
    incoming = Invoice.objects.filter(invoice_type=InvoiceType.INCOMING, issue_date__year=year, issue_date__month=month)
    approved_shifts = Shift.objects.filter(status=ShiftStatus.APPROVED, start_time__year=year, start_time__month=month)

    total_revenue = sum(inv.total_amount for inv in outgoing)
    total_costs = sum(inv.total_amount for inv in incoming)
    total_payroll = sum(s.total_cost for s in approved_shifts)
    net_profit = total_revenue - total_costs - Decimal(str(total_payroll))

    context = {
        'year': year,
        'month': month,
        'total_revenue': total_revenue,
        'total_costs': total_costs,
        'total_payroll': round(total_payroll, 2),
        'net_profit': round(net_profit, 2),
    }
    return render(request, 'portals/portal_owner.html', context)