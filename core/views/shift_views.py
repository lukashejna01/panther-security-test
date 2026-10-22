"""
Pohledy pro plánování směn, dispečerský kalendář, schvalování docházky
a mobilní check-in / check-out strážného na stanovišti.
"""

from datetime import date, datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.models import GuardObject, Shift, ShiftStatus, SystemRole, Candidate
from core.forms import ShiftCreateForm


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def shift_planner_calendar_view(request):
    """
    Přehledný kalendář dispečinku:
    - Zobrazuje pro každý den, kdo, kde a na jakém objektu slouží.
    - Zobrazuje naplánované pohovory se zájemci.
    - Možnost vypsat novou směnu nebo obsadit volnou.
    """
    now = timezone.now()
    selected_date_str = request.GET.get('date', now.strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = now.date()

    # Všechny střežené objekty a jejich směny na vybraný den
    objects = GuardObject.objects.filter(is_active=True).prefetch_related('client')
    day_shifts = Shift.objects.filter(
        start_time__date=selected_date
    ).select_related('guard_object', 'employee', 'required_position').order_by('start_time')

    # Naplánované pohovory na vybraný den
    day_interviews = Candidate.objects.filter(
        interview_date__date=selected_date,
        is_archived=False
    ).order_by('interview_date')

    # Formulář pro rychlé vypsání směny
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
            messages.success(request, f"Směna pro {shift.guard_object.name} byla úspěšně vytvořena.")
            return redirect(f"{request.path}?date={selected_date.strftime('%Y-%m-%d')}")

    context = {
        'selected_date': selected_date,
        'day_shifts': day_shifts,
        'day_interviews': day_interviews,
        'objects': objects,
        'form': form,
    }
    return render(request, 'shifts/shift_planner_calendar.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def approve_shift_view(request, shift_id):
    """
    Schválení směny manažerem/majitelem:
    PRAVIDLO: Směnu lze schválit POUZE pokud již skončila v minulosti!
    Po schválení se okamžitě propisuje do mzdového systému.
    """
    shift = get_object_or_404(Shift, id=shift_id)

    if not shift.can_be_approved:
        messages.error(
            request,
            "Tuto směnu nelze schválit! Schvalovat lze pouze směny, které již reálně skončily (nikoli do budoucna) a mají přiřazeného strážného."
        )
        return redirect('manager_dashboard')

    manager_profile = getattr(request.user, 'employee_profile', None)
    shift.status = ShiftStatus.APPROVED
    shift.approved_by = manager_profile
    shift.approved_at = timezone.now()
    shift.save()

    messages.success(
        request,
        f"Směna #{shift.id} ({shift.employee.full_name}) byla schválena a {shift.total_cost} Kč bylo připsáno do mezd."
    )
    return redirect('manager_dashboard')


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def shift_detail_view(request, shift_id):
    """Detail směny, směrnice a odbavení docházky (Check-in / Check-out)."""
    profile = getattr(request.user, 'employee_profile', None)
    shift = get_object_or_404(
        Shift.objects.select_related('guard_object', 'guard_object__client', 'employee'),
        id=shift_id
    )

    if profile.system_role == SystemRole.STAFF and shift.employee != profile:
        messages.error(request, "K této směně nemáte přístup.")
        return redirect('employee_portal')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'check_in':
            if shift.status in [ShiftStatus.ASSIGNED, ShiftStatus.OPEN]:
                shift.actual_start_time = timezone.now()
                shift.status = ShiftStatus.IN_PROGRESS
                shift.save()
                messages.success(request, f"Nastoupil jste do služby ({shift.actual_start_time.strftime('%H:%M')}).")
            return redirect('shift_detail', shift_id=shift.id)

        elif action == 'check_out':
            if shift.status == ShiftStatus.IN_PROGRESS:
                shift.actual_end_time = timezone.now()
                shift.guard_notes = request.POST.get('guard_notes', '').strip()
                shift.status = ShiftStatus.COMPLETED
                shift.save()
                messages.success(request, "Služba ukončena. Odesláno dispečinku ke schválení.")
            return redirect('shift_detail', shift_id=shift.id)

    return render(request, 'shifts/shift_detail.html', {'shift': shift})


@login_required
@role_required([SystemRole.STAFF, SystemRole.MANAGER, SystemRole.OWNER])
def claim_shift_view(request, shift_id):
    """Převzetí volné směny z burzy strážným."""
    profile = getattr(request.user, 'employee_profile', None)
    shift = get_object_or_404(Shift, id=shift_id)

    if shift.status != ShiftStatus.OPEN:
        messages.error(request, "Tato směna již není k dispozici.")
        return redirect('employee_portal')

    shift.employee = profile
    shift.status = ShiftStatus.ASSIGNED
    shift.save()
    messages.success(request, f"Směna na objektu {shift.guard_object.name} byla zařazena do vašeho rozpisu.")
    return redirect('employee_portal')