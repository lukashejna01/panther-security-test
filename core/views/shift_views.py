"""
Pohledy pro plánování směn, dispečerský kalendář ve stylu Google Kalendáře
(den, týden, měsíc s postranním minikalendářem) a schvalování docházky.
"""

from datetime import datetime, timedelta, date
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
    Dispečerský kalendář ve stylu Google Kalendáře:
    - Postranní lišta: minikalendář + filtry (objekty, pracovníci).
    - Zobrazení: Den (day), Týden (week), Měsíc (month).
    """
    _auto_complete_expired_shifts()
    now = timezone.now()
    selected_date_str = request.GET.get('date', now.strftime('%Y-%m-%d'))
    view_type = request.GET.get('view', 'week')  # 'day', 'week', 'month'
    filter_obj = request.GET.get('object_id', '')
    filter_emp = request.GET.get('employee_id', '')

    try:
        current_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = now.date()

    # --- 1. MINIKALENDÁŘ PRO POST RANNÍ LIŠTU ---
    cal = calendar.Calendar(firstweekday=0)
    mini_weeks = cal.monthdatescalendar(current_date.year, current_date.month)
    mini_month_weeks = []
    for week in mini_weeks:
        week_days = []
        for d in week:
            week_days.append({
                'date': d,
                'day_num': d.day,
                'is_current_month': d.month == current_date.month,
                'is_selected': d == current_date,
                'is_today': d == now.date(),
            })
        mini_month_weeks.append(week_days)

    czech_months = [
        '', 'leden', 'únor', 'březen', 'duben', 'květen', 'červen',
        'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec'
    ]
    mini_title = f"{czech_months[current_date.month].capitalize()} {current_date.year}"

    # Navigace minikalendáře (předchozí a další měsíc)
    prev_month_date = (current_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month_date = (current_date.replace(day=28) + timedelta(days=5)).replace(day=1)

    # --- 2. VÝPOČET ROZSAHU PODLE ZVOLENÉHO POHLEDU ---
    if view_type == 'day':
        start_range = current_date
        end_range = current_date
        prev_nav_date = current_date - timedelta(days=1)
        next_nav_date = current_date + timedelta(days=1)
        period_title = f"{current_date.day}. {czech_months[current_date.month]} {current_date.year}"
    elif view_type == 'month':
        start_range = current_date.replace(day=1)
        if current_date.month == 12:
            end_range = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_range = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)
        prev_nav_date = (current_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        next_nav_date = (current_date.replace(day=28) + timedelta(days=5)).replace(day=1)
        period_title = f"{czech_months[current_date.month].capitalize()} {current_date.year}"
    else:  # 'week' je výchozí
        view_type = 'week'
        start_range = current_date - timedelta(days=current_date.weekday())  # Pondělí
        end_range = start_range + timedelta(days=6)  # Neděle
        prev_nav_date = current_date - timedelta(days=7)
        next_nav_date = current_date + timedelta(days=7)
        if start_range.month == end_range.month:
            period_title = f"{start_range.day}. – {end_range.day}. {czech_months[start_range.month]} {start_range.year}"
        else:
            period_title = f"{start_range.day}. {czech_months[start_range.month]} – {end_range.day}. {czech_months[end_range.month]} {end_range.year}"

    # --- 3. NAČTENÍ A FILTROVÁNÍ SMĚN ---
    start_dt = timezone.make_aware(datetime.combine(start_range, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_range, datetime.max.time()))

    shifts_qs = Shift.objects.filter(
        start_time__lte=end_dt,
        end_time__gte=start_dt
    ).exclude(status=ShiftStatus.CANCELLED).select_related(
        'guard_object', 'guard_object__client', 'employee'
    ).order_by('start_time')

    if filter_obj:
        shifts_qs = shifts_qs.filter(guard_object_id=filter_obj)
    if filter_emp:
        shifts_qs = shifts_qs.filter(employee_id=filter_emp)

    shifts_list = list(shifts_qs)

    # --- 4. STRUKTURA PRO JEDNOTLIVÉ POHLEDY ---
    # A) TÝDENNÍ POHLED: 7 dní
    week_columns = []
    czech_day_names = ['PO', 'ÚT', 'ST', 'ČT', 'PÁ', 'SO', 'NE']
    if view_type == 'week':
        for i in range(7):
            d = start_range + timedelta(days=i)
            day_shifts = [s for s in shifts_list if s.start_time.date() <= d <= s.end_time.date()]
            week_columns.append({
                'date': d,
                'day_name': czech_day_names[d.weekday()],
                'day_num': d.day,
                'is_today': d == now.date(),
                'is_selected': d == current_date,
                'shifts': day_shifts,
            })

    # B) DENNÍ POHLED: směny pro vybraný den
    day_shifts = []
    if view_type == 'day':
        day_shifts = [s for s in shifts_list if s.start_time.date() <= current_date <= s.end_time.date()]

    # C) MĚSÍČNÍ POHLED: matice týdnů
    month_grid = []
    if view_type == 'month':
        cal_month_days = cal.monthdatescalendar(current_date.year, current_date.month)
        for w in cal_month_days:
            week_row = []
            for d in w:
                cell_shifts = [s for s in shifts_list if s.start_time.date() <= d <= s.end_time.date()]
                week_row.append({
                    'date': d,
                    'day_num': d.day,
                    'is_current_month': d.month == current_date.month,
                    'is_today': d == now.date(),
                    'is_selected': d == current_date,
                    'shifts': cell_shifts,
                })
            month_grid.append(week_row)

    # Hodinová časová osa pro denní/týdenní pohled (od 06:00 do 22:00 po 2 hodinách)
    hours_timeline = [f"{h:02d}:00" for h in range(6, 23, 2)]

    # --- 5. DATA PRO FILTRY A FORMULÁŘ ---
    active_objects = GuardObject.objects.filter(is_active=True).order_by('name')
    active_employees = Employee.objects.filter(is_active=True, is_archived=False).order_by('last_name')

    form = ShiftCreateForm(initial={
        'start_time': timezone.make_aware(datetime.combine(current_date, datetime.min.time().replace(hour=7))),
        'end_time': timezone.make_aware(datetime.combine(current_date, datetime.min.time().replace(hour=19))),
    })

    if request.method == 'POST' and 'create_shift' in request.POST:
        form = ShiftCreateForm(request.POST)
        if form.is_valid():
            shift = form.save(commit=False)
            if shift.employee:
                shift.status = ShiftStatus.ASSIGNED
            else:
                shift.status = ShiftStatus.OPEN
            if not shift.hourly_rate:
                shift.hourly_rate = shift.guard_object.hourly_rate_cost
            shift.save()
            messages.success(request, f"Směna pro {shift.guard_object.name} byla úspěšně vypsána.")
            return redirect(f"{request.path}?date={current_date.strftime('%Y-%m-%d')}&view={view_type}&object_id={filter_obj}&employee_id={filter_emp}")

    context = {
        'current_date': current_date,
        'view_type': view_type,
        'period_title': period_title,
        'is_today': current_date == now.date(),
        'prev_nav_date': prev_nav_date,
        'next_nav_date': next_nav_date,
        # Minikalendář
        'mini_title': mini_title,
        'mini_month_weeks': mini_month_weeks,
        'prev_month_date': prev_month_date,
        'next_month_date': next_month_date,
        # Pohledy
        'week_columns': week_columns,
        'day_shifts': day_shifts,
        'month_grid': month_grid,
        'hours_timeline': hours_timeline,
        # Filtry
        'active_objects': active_objects,
        'active_employees': active_employees,
        'filter_obj': filter_obj,
        'filter_emp': filter_emp,
        'total_shifts_count': len(shifts_list),
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