"""
Pohledy pro plánování směn, dispečerský kalendář (dle objektů i dle zaměstnanců)
a schvalování odsloužené docházky.
"""

from datetime import datetime, timedelta
import calendar
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.models import GuardObject, Shift, ShiftStatus, SystemRole, Candidate, Employee
from core.forms import ShiftCreateForm


def _auto_complete_expired_shifts():
    """Pomocná funkce: převede všechny skončené směny do stavu COMPLETED (čeká na schválení)."""
    now = timezone.now()
    Shift.objects.filter(
        status__in=[ShiftStatus.ASSIGNED, ShiftStatus.IN_PROGRESS],
        end_time__lte=now,
        employee__isnull=False
    ).update(status=ShiftStatus.COMPLETED)


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def employee_calendar_view(request):
    """Měsíční kalendář směn pro přihlášeného strážného."""
    profile = getattr(request.user, 'employee_profile', None)
    if not profile:
        messages.error(request, "Váš uživatelský účet nemá přiřazen profil zaměstnance.")
        return redirect('home')

    _auto_complete_expired_shifts()
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    cal = calendar.Calendar(firstweekday=0) # Pondělí jako první den
    month_days = cal.monthdatescalendar(year, month)

    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(seconds=1)

    shifts = Shift.objects.filter(
        employee=profile,
        start_time__gte=timezone.make_aware(first_day),
        start_time__lte=timezone.make_aware(last_day)
    ).select_related('guard_object').order_by('start_time')

    shifts_by_date = {}
    for s in shifts:
        s_date = s.start_time.date()
        shifts_by_date.setdefault(s_date, []).append(s)

    calendar_weeks = []
    for week in month_days:
        week_data = []
        for d in week:
            week_data.append({
                'date': d,
                'is_current_month': d.month == month,
                'is_today': d == now.date(),
                'shifts': shifts_by_date.get(d, []),
            })
        calendar_weeks.append(week_data)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    context = {
        'profile': profile,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'calendar_weeks': calendar_weeks,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
    }
    return render(request, 'shifts/employee_calendar.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def shift_planner_calendar_view(request):
    """
    Plánovač a dispečerský kalendář se dvěma pohledy na vybraný den:
    1. Pohled dle OBJEKTŮ (všechna stanoviště a rozpis na nich)
    2. Pohled dle ZAMĚSTNANCŮ (všichni pracovníci a jejich naplánované směny)
    """
    _auto_complete_expired_shifts()
    now = timezone.now()
    selected_date_str = request.GET.get('date', now.strftime('%Y-%m-%d'))
    view_mode = request.GET.get('mode', 'objects') # 'objects' nebo 'employees'

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = now.date()

    prev_day = selected_date - timedelta(days=1)
    next_day = selected_date + timedelta(days=1)

    # Všechny směny na daný den
    day_shifts = Shift.objects.filter(
        start_time__date=selected_date
    ).select_related('guard_object', 'guard_object__client', 'employee', 'required_position').order_by('start_time')

    # Režim A: Data seskupená dle OBJEKTŮ
    objects_data = []
    active_objects = GuardObject.objects.filter(is_active=True).select_related('client').order_by('name')
    for obj in active_objects:
        obj_shifts = [s for s in day_shifts if s.guard_object_id == obj.id]
        objects_data.append({
            'object': obj,
            'shifts': obj_shifts,
            'has_shifts': len(obj_shifts) > 0,
        })

    # Režim B: Data seskupená dle ZAMĚSTNANCŮ
    employees_data = []
    active_employees = Employee.objects.filter(is_active=True, is_archived=False).order_by('last_name', 'first_name')
    for emp in active_employees:
        emp_shifts = [s for s in day_shifts if s.employee_id == emp.id]
        employees_data.append({
            'employee': emp,
            'shifts': emp_shifts,
            'is_busy': len(emp_shifts) > 0,
        })

    # Formulář pro rychlé vytvoření směny
    form = ShiftCreateForm(initial={
        'start_time': timezone.make_aware(datetime.combine(selected_date, datetime.min.time().replace(hour=7))),
        'end_time': timezone.make_aware(datetime.combine(selected_date, datetime.min.time().replace(hour=19))),
    })

    if request.method == 'POST' and 'create_shift' in request.POST:
        form = ShiftCreateForm(request.POST)
        if form.is_valid():
            shift = form.save(commit=False)
            if shift.employee:
                shift.status = ShiftStatus.ASSIGNED
            else:
                shift.status = ShiftStatus.OPEN
            shift.save()
            messages.success(request, f"Směna pro {shift.guard_object.name} byla úspěšně vypsána.")
            return redirect(f"{request.path}?date={selected_date.strftime('%Y-%m-%d')}&mode={view_mode}")

    context = {
        'selected_date': selected_date,
        'prev_day': prev_day,
        'next_day': next_day,
        'is_today': selected_date == now.date(),
        'view_mode': view_mode,
        'objects_data': objects_data,
        'employees_data': employees_data,
        'total_shifts_count': day_shifts.count(),
        'form': form,
    }
    return render(request, 'shifts/shift_planner_calendar.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def approve_shift_view(request, shift_id):
    """Schválení směny manažerem/majitelem po jejím uplynutí."""
    _auto_complete_expired_shifts()
    shift = get_object_or_404(Shift, id=shift_id)

    if not shift.can_be_approved:
        messages.error(
            request,
            "Tuto směnu nelze schválit! Schvalovat lze pouze směny, které již skončily a mají přiřazeného strážného."
        )
        return redirect('manager_dashboard')

    manager_profile = getattr(request.user, 'employee_profile', None)
    shift.status = ShiftStatus.APPROVED
    shift.approved_by = manager_profile
    shift.approved_at = timezone.now()
    shift.save()

    messages.success(
        request,
        f"Směna #{shift.id} ({shift.employee.full_name}) byla schválena. {shift.total_cost} Kč bylo připsáno do mezd."
    )
    return redirect('manager_dashboard')


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def shift_detail_view(request, shift_id):
    """Informační detail směny pro strážného (instrukce, adresa, kontakty)."""
    profile = getattr(request.user, 'employee_profile', None)
    shift = get_object_or_404(
        Shift.objects.select_related('guard_object', 'guard_object__client', 'employee'),
        id=shift_id
    )

    if profile.system_role == SystemRole.STAFF and shift.employee != profile and shift.status != ShiftStatus.OPEN:
        messages.error(request, "K této směně nemáte přístup.")
        return redirect('employee_portal')

    return render(request, 'shifts/shift_detail.html', {'shift': shift})


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def claim_shift_view(request, shift_id):
    """Převzetí volné směny z burzy strážným."""
    profile = getattr(request.user, 'employee_profile', None)
    shift = get_object_or_404(Shift, id=shift_id)

    if shift.status != ShiftStatus.OPEN:
        messages.error(request, "Tato směna již není volná k převzetí.")
        return redirect('employee_portal')

    shift.employee = profile
    shift.status = ShiftStatus.ASSIGNED
    shift.save()
    messages.success(request, f"Směna na stanovišti {shift.guard_object.name} byla zařazena do vašeho rozpisu.")
    return redirect('employee_portal')