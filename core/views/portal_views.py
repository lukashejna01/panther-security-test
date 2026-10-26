"""
Hlavní portály:
- Portál strážného (týdenní náhled 7 dní, čekající na podpis, schválené do mzdy, burza)
- Dispečink manažera (čekající směny ke schválení, přehled stanovišť)
- Kokpit majitele (ziskovost, ekonomika, marže)
"""

from decimal import Decimal
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from core.decorators import role_required
from core.models import Candidate, GuardObject, Invoice, InvoiceType, Shift, ShiftStatus, SystemRole
from core.views.shift_views import _auto_complete_expired_shifts


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def employee_portal_view(request):
    """
    Portál zaměstnance bez manuálního check-inu:
    - Přehled nadcházejících směn na nejbližších 7 dní
    - Odsloužené směny čekající na schválení manažerem (automaticky po uplynutí konce směny)
    - Schválené směny v aktuálním měsíci připsané do mzdy
    - Burza volných směn
    """
    _auto_complete_expired_shifts()
    profile = getattr(request.user, 'employee_profile', None)
    now = timezone.now()
    seven_days_later = now + timedelta(days=7)

    upcoming_week_shifts = []
    pending_shifts = []
    approved_shifts = []
    month_earned = 0.0
    month_hours = 0.0

    if profile:
        # Plánované budoucí směny na příštích 7 dní
        upcoming_week_shifts = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.ASSIGNED,
            start_time__gte=now,
            start_time__lte=seven_days_later
        ).select_related('guard_object').order_by('start_time')

        # Odslouženo - čeká na schválení manažerem
        pending_shifts = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.COMPLETED
        ).select_related('guard_object').order_by('-end_time')

        # Schváleno v aktuálním měsíci (připsáno do mzdy)
        first_day_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        approved_shifts = Shift.objects.filter(
            employee=profile,
            status=ShiftStatus.APPROVED,
            start_time__gte=first_day_month
        ).select_related('guard_object').order_by('-start_time')

        for s in approved_shifts:
            month_hours += float(s.planned_hours)
            month_earned += float(s.total_cost)

    # Volné směny z burzy k rozebrání
    open_shifts = Shift.objects.filter(
        status=ShiftStatus.OPEN,
        start_time__gte=now
    ).exclude(employee=profile).select_related('guard_object').order_by('start_time')

    context = {
        'profile': profile,
        'upcoming_week_shifts': upcoming_week_shifts,
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
    """Dispečerský portál manažera se směnami čekajícími na schválení."""
    _auto_complete_expired_shifts()
    now = timezone.now()

    shifts_to_approve = Shift.objects.filter(
        status=ShiftStatus.COMPLETED
    ).select_related('guard_object', 'employee').order_by('-end_time')

    open_market = Shift.objects.filter(status=ShiftStatus.OPEN, start_time__gte=now).count()
    active_candidates_count = Candidate.objects.filter(is_archived=False).count()

    context = {
        'shifts_to_approve': shifts_to_approve,
        'open_market_count': open_market,
        'active_candidates_count': active_candidates_count,
    }
    return render(request, 'portals/portal_manager.html', context)


@login_required
@role_required([SystemRole.OWNER])
def owner_dashboard_view(request):
    """
    Manažerský a ekonomický kokpit majitele: ziskovost objektů, tržby vs. náklady.
    """
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    # 1. Tržby z vydaných faktur
    outgoing_invoices = Invoice.objects.filter(
        invoice_type=InvoiceType.OUTGOING,
        issue_date__year=year,
        issue_date__month=month
    )
    total_revenue = sum(inv.total_amount for inv in outgoing_invoices)

    # 2. Provozní náklady od dodavatelů
    incoming_invoices = Invoice.objects.filter(
        invoice_type=InvoiceType.INCOMING,
        issue_date__year=year,
        issue_date__month=month
    )
    total_supplier_costs = sum(inv.total_amount for inv in incoming_invoices)

    # 3. Mzdové náklady na strážné za schválené směny
    month_approved_shifts = Shift.objects.filter(
        status=ShiftStatus.APPROVED,
        start_time__year=year,
        start_time__month=month
    )
    total_payroll = sum(s.total_cost for s in month_approved_shifts)

    # 4. Celkový zisk a marže
    total_expenses = total_supplier_costs + Decimal(str(total_payroll))
    net_profit = total_revenue - total_expenses
    margin_percent = round((float(net_profit) / float(total_revenue) * 100), 1) if total_revenue > 0 else 0.0

    # 5. Seznamy pro roletky měsíců a let
    months_list = [
        (1, 'Leden'), (2, 'Únor'), (3, 'Březen'), (4, 'Duben'),
        (5, 'Květen'), (6, 'Červen'), (7, 'Červenec'), (8, 'Srpen'),
        (9, 'Září'), (10, 'Říjen'), (11, 'Listopad'), (12, 'Prosinec')
    ]
    available_years = list(range(now.year - 2, now.year + 3))

    context = {
        'year': year,
        'month': month,
        'months_list': months_list,
        'available_years': available_years,
        'total_revenue': total_revenue,
        'total_supplier_costs': total_supplier_costs,
        'total_payroll': round(total_payroll, 2),
        'total_expenses': total_expenses,
        'net_profit': round(net_profit, 2),
        'margin_percent': margin_percent,
    }
    return render(request, 'portals/portal_owner.html', context)