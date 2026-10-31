"""
Pohledy pro náborovou pipeline, evidenci zájemců, plánování pohovorů,
samostatný archiv zájemců a převod zájemce na kmenového zaměstnance (OCR dokladu a ČSSZ ONZ).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.models import Candidate, CandidateStatus, Employee, SystemRole
from core.forms import (
    CandidateCreateForm,
    CandidateInterviewScheduleForm,
    CandidateStatusUpdateForm,
    CandidateArchiveForm,
    IDCardUploadForm,
    EmployeeOnboardingForm,
)
from core.services import extract_data_from_id, generate_onz_xml
from .auth_views import generate_credentials


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def candidate_list_view(request):
    """
    Aktivní náborová pipeline zájemců o práci:
    - Seznam aktivních uchazečů (mimo archiv)
    - Rychlé přidání nového zájemce s volitelným pohovorem a evidencí autora
    - Přehled naplánovaných pohovorů
    """
    form = CandidateCreateForm()

    if request.method == 'POST':
        form = CandidateCreateForm(request.POST)
        if form.is_valid():
            cand = form.save(commit=False)
            cand.created_by = request.user  # Uložení uživatele, který zájemce vytvořil
            if cand.interview_date:
                cand.status = CandidateStatus.INTERVIEW
            cand.save()
            messages.success(request, f"Zájemce {cand.full_name} byl úspěšně zaevidován do náboru.")
            return redirect('candidate_list')
        else:
            messages.error(request, "Zkontrolujte zadané údaje zájemce.")

    active_candidates = Candidate.objects.filter(is_archived=False).select_related('created_by')
    
    # Uchazeči rozdělení dle fází
    new_candidates = active_candidates.filter(status=CandidateStatus.NEW)
    interview_candidates = active_candidates.filter(status=CandidateStatus.INTERVIEW).order_by('interview_date')
    approved_candidates = active_candidates.filter(status=CandidateStatus.APPROVED)

    context = {
        'form': form,
        'new_candidates': new_candidates,
        'interview_candidates': interview_candidates,
        'approved_candidates': approved_candidates,
        'total_active': active_candidates.count(),
    }
    return render(request, 'candidates/candidate_pipeline.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def schedule_interview_view(request, candidate_id):
    """Plánování nebo změna termínu pohovoru zájemce."""
    candidate = get_object_or_404(Candidate, id=candidate_id, is_archived=False)
    form = CandidateInterviewScheduleForm(instance=candidate)

    if request.method == 'POST':
        form = CandidateInterviewScheduleForm(request.POST, instance=candidate)
        if form.is_valid():
            cand = form.save(commit=False)
            if cand.interview_date and cand.status == CandidateStatus.NEW:
                cand.status = CandidateStatus.INTERVIEW
            cand.save()
            messages.success(request, f"Pohovor pro {cand.full_name} byl naplánován na {cand.interview_date.strftime('%d.%m.%Y %H:%M')}.")
            return redirect('candidate_list')

    context = {
        'candidate': candidate,
        'form': form,
    }
    return render(request, 'candidates/candidate_schedule.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def archive_candidate_view(request, candidate_id):
    """Vyřazení zájemce do samostatného archivu s důvodem."""
    candidate = get_object_or_404(Candidate, id=candidate_id)
    form = CandidateArchiveForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        candidate.is_archived = True
        candidate.status = CandidateStatus.REJECTED
        candidate.rejection_reason = form.cleaned_data['rejection_reason']
        candidate.save()
        messages.info(request, f"Zájemce {candidate.full_name} byl přesunut do archivu.")
        return redirect('candidate_list')

    return render(request, 'candidates/candidate_archive_confirm.html', {'candidate': candidate, 'form': form})


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def candidates_archive_list_view(request):
    """Samostatný archiv zájemců o práci."""
    archived = Candidate.objects.filter(is_archived=True).select_related('created_by').order_by('-updated_at')
    return render(request, 'candidates/candidates_archive_list.html', {'archived_candidates': archived})


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def candidate_onboard_view(request, candidate_id):
    """
    Onboarding proces:
    1. Sken / PDF dokladu totožnosti vytěžen přes Claude OCR.
    2. Formulář s výběrem zdravotní pojišťovny (Kód - Název) a datem nástupu pro ČSSZ.
    3. Převedení zájemce do kmene zaměstnanců, založení účtu a zobrazení hesla přímo v seznamu zaměstnanců.
    """
    candidate = get_object_or_404(Candidate, id=candidate_id, is_archived=False)
    upload_form = IDCardUploadForm()
    
    # Výchozí data
    initial_employee_data = {
        'first_name': candidate.first_name,
        'last_name': candidate.last_name,
        'phone': candidate.phone,
        'email': candidate.email,
        'start_employment_date': timezone.now().date(),
    }
    employee_form = EmployeeOnboardingForm(initial=initial_employee_data)

    if request.method == 'POST':
        # 1. OCR Sken dokladu
        if 'scan_id' in request.POST:
            upload_form = IDCardUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                try:
                    file_obj = request.FILES['id_card_image']
                    data = extract_data_from_id(file_obj)

                    extracted_data = {
                        'first_name': data.get('first_name') or candidate.first_name,
                        'last_name': data.get('last_name') or candidate.last_name,
                        'birth_date': data.get('birth_date') or None,
                        'birth_number': data.get('birth_number', ''),
                        'id_card_number': data.get('id_card_number', ''),
                        'street': data.get('street', ''),
                        'house_number': data.get('house_number', ''),
                        'orientation_number': data.get('orientation_number', ''),
                        'city': data.get('city', ''),
                        'zip_code': data.get('zip_code', ''),
                        'phone': candidate.phone,
                        'email': candidate.email,
                        'start_employment_date': timezone.now().date(),
                    }
                    employee_form = EmployeeOnboardingForm(initial=extracted_data)
                    messages.success(request, "Doklad totožnosti byl úspěšně vytěžen přes Claude AI. Zkontrolujte formulář a potvrďte nástup.")
                except Exception as e:
                    messages.error(request, f"Chyba Claude OCR: {e}")
            else:
                messages.error(request, "Vyberte platný soubor dokladu (PDF/obrázek).")

        # 2. Uložení zaměstnance, vytvoření účtu a přesměrování do seznamu zaměstnanců
        elif 'save_employee' in request.POST:
            employee_form = EmployeeOnboardingForm(request.POST)
            if employee_form.is_valid():
                employee = employee_form.save(commit=False)
                fn = employee.first_name.strip()
                ln = employee.last_name.strip()

                username, raw_password = generate_credentials(fn, ln)
                user = User.objects.create_user(
                    username=username,
                    email=employee.email,
                    password=raw_password,
                    first_name=fn,
                    last_name=ln
                )
                employee.user = user
                employee.generated_password = raw_password  # Uložení hesla pro manažerský přehled
                employee.system_role = SystemRole.STAFF
                employee.is_active = True
                employee.save()

                candidate.status = CandidateStatus.HIRED
                candidate.save()

                # Výrazná flash zpráva s heslem a přesměrování přímo na kmen zaměstnanců
                messages.success(
                    request,
                    f"🎉 Zaměstnanec {fn} {ln} byl úspěšně zařazen do kmene! "
                    f"Přihlašovací jméno: {username} | Dočasné heslo: {raw_password} (předejte zaměstnanci)"
                )
                return redirect('employee_list')
            else:
                messages.error(request, "Zkontrolujte prosím chyby ve formuláři nástupu.")

    context = {
        'candidate': candidate,
        'upload_form': upload_form,
        'employee_form': employee_form,
    }
    return render(request, 'candidates/candidate_onboard.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def download_cssz_onz_view(request, employee_id):
    """Vygeneruje a stáhne oficiální XML balíček ČSSZ ONZ2022 pro oznámení nástupu."""
    employee = get_object_or_404(Employee, id=employee_id)
    xml_content = generate_onz_xml(employee)

    employee.is_reported_cssz = True
    employee.reported_cssz_date = timezone.now()
    employee.save(update_fields=['is_reported_cssz', 'reported_cssz_date'])

    response = HttpResponse(xml_content, content_type='application/xml; charset=utf-8')
    filename = f"ONZ_{employee.last_name}_{employee.birth_number or employee.id}.xml"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response