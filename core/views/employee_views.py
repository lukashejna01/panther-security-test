"""
Pohledy pro kmenové zaměstnance Panther Security a samostatný archiv zaměstnanců
(ukončené pracovní poměry) včetně smluv a dokumentů o ukončení v PDF.
"""

import unicodedata

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import role_required
from core.models import Employee, SystemRole
from core.forms import EmployeeArchiveForm
from core.forms.employee_forms import EmployeeCsszDataForm
from core.services import (
    RegzecDataError,
    build_regzec_xml,
    check_regzec_data,
    has_contract_template,
    has_termination_template,
    store_contract_pdf,
    store_termination_pdf,
)
from core.services.contract_pdf import NOTICE_PERIOD_DAYS
from core.services.cssz_submit import (
    IsdsError,
    check_protocols,
    cssz_databox,
    isds_configured,
    isds_environment,
    submit_regzec,
)


def _serve_employee_pdf(request, employee, file_field, label):
    """
    Vydá PDF uložené na kartě zaměstnance. Dokumenty obsahují rodné číslo,
    proto jdou jen přes pohledy s kontrolou role – ne přímým odkazem do /media/.
    """
    pdf = getattr(employee, file_field)
    if not pdf:
        messages.error(request, f"Zaměstnanec zatím nemá vygenerovaný dokument: {label}.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        pdf_file = pdf.open('rb')
    except FileNotFoundError:
        messages.error(request, f"Soubor ({label}) na serveru chybí. Vygenerujte ho znovu.")
        return redirect('employee_detail', employee_id=employee.id)

    filename = f"{label}_{employee.last_name}_{employee.first_name}.pdf".replace(' ', '_')
    return FileResponse(pdf_file, content_type='application/pdf', as_attachment=False, filename=filename)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_list_view(request):
    """Kmenový přehled aktivních zaměstnanců Panther Security."""
    employees = Employee.objects.filter(is_active=True, is_archived=False).select_related('department', 'position').order_by('last_name')
    return render(request, 'employees/employee_list.html', {'employees': employees})


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_detail_view(request, employee_id):
    """Karta zaměstnance s osobními údaji, smlouvou a historií směn."""
    employee = get_object_or_404(Employee, id=employee_id)
    shifts = employee.shifts.select_related('guard_object').order_by('-start_time')[:10]

    show_cssz = employee.is_active and not employee.is_reported_cssz
    context = {
        'employee': employee,
        'shifts': shifts,
        'has_contract_template': has_contract_template(employee.contract_type),
        'has_termination_template': has_termination_template(employee.contract_type, employee.termination_type),
        'show_cssz': show_cssz,
        'cssz_problems': check_regzec_data(employee) if show_cssz else [],
        'cssz_test_enabled': bool(getattr(settings, 'CSSZ_TEST_VS', '')),
        'cssz_submissions': employee.cssz_submissions.select_related('sent_by')[:10],
        'isds_configured': isds_configured(),
        'isds_environment': isds_environment(),
        'cssz_databox': cssz_databox(isds_environment()),
    }
    return render(request, 'employees/employee_detail.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_contract_view(request, employee_id):
    """Zobrazení smlouvy v PDF."""
    employee = get_object_or_404(Employee, id=employee_id)
    return _serve_employee_pdf(request, employee, 'contract_pdf', f"Smlouva {employee.contract_type}")


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_contract_regenerate_view(request, employee_id):
    """Nové vygenerování smlouvy (po opravě údajů nebo změně vzoru). Stará verze se nahradí."""
    employee = get_object_or_404(Employee, id=employee_id)
    if not has_contract_template(employee.contract_type):
        messages.error(request, f"Pro typ smlouvy {employee.get_contract_type_display()} zatím není připraven vzor.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        store_contract_pdf(employee)
        messages.success(request, f"Smlouva {employee.contract_type} pro {employee.full_name} byla vygenerována.")
    except Exception as e:
        messages.error(request, f"Smlouvu se nepodařilo vygenerovat: {e}")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_termination_view(request, employee_id):
    """Zobrazení dokumentu o ukončení (výpověď / dohoda o ukončení) v PDF."""
    employee = get_object_or_404(Employee, id=employee_id)
    label = employee.get_termination_type_display() or "Ukončení"
    return _serve_employee_pdf(request, employee, 'termination_pdf', label)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_termination_regenerate_view(request, employee_id):
    """Nové vygenerování dokumentu o ukončení z aktuálních údajů na kartě."""
    employee = get_object_or_404(Employee, id=employee_id, is_archived=True)
    if not has_termination_template(employee.contract_type, employee.termination_type):
        messages.error(request, "Pro tento typ smlouvy a způsob ukončení zatím není připraven vzor dokumentu.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        store_termination_pdf(employee)
        messages.success(request, f"Dokument „{employee.get_termination_type_display()}“ byl vygenerován.")
    except Exception as e:
        messages.error(request, f"Dokument o ukončení se nepodařilo vygenerovat: {e}")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_cssz_xml_view(request, employee_id):
    """
    Stažení přihlášky zaměstnance na ČSSZ (REGZEC, akce 1 – nástup) jako XML pro datovou schránku.
    ?test=1 použije fiktivní VS pro testovací prostředí ČSSZ (schránka 9tsaf6s).
    """
    employee = get_object_or_404(Employee, id=employee_id)
    test = request.GET.get('test') == '1'

    try:
        xml_bytes, year = build_regzec_xml(employee, test=test)
    except RegzecDataError as e:
        for problem in e.problems:
            messages.error(request, problem)
        return redirect('employee_detail', employee_id=employee.id)

    prefix = 'TEST_' if test else ''
    surname = unicodedata.normalize('NFKD', employee.last_name).encode('ascii', 'ignore').decode() or 'zamestnanec'
    filename = f"{prefix}REGZEC{year % 100}_{surname}_{employee.start_employment_date:%Y%m%d}.xml"
    response = HttpResponse(xml_bytes, content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_cssz_data_view(request, employee_id):
    """Doplnění údajů, které ČSSZ vyžaduje pro přihlášku zaměstnance."""
    employee = get_object_or_404(Employee, id=employee_id)
    initial = {}
    if not employee.work_municipality:
        initial['work_municipality'] = getattr(settings, 'CSSZ_DEFAULT_MUNICIPALITY', '')
    if not employee.work_municipality_code:
        initial['work_municipality_code'] = getattr(settings, 'CSSZ_DEFAULT_MUNICIPALITY_CODE', '')
    if not employee.birth_surname:
        initial['birth_surname'] = employee.last_name

    form = EmployeeCsszDataForm(request.POST or None, instance=employee, initial=initial)
    if request.method == 'POST' and form.is_valid():
        form.save()
        problems = check_regzec_data(employee)
        if problems:
            messages.warning(request, "Údaje uloženy. Pro podání ještě chybí: " + " ".join(problems))
        else:
            messages.success(request, "Údaje uloženy. Přihlášku na ČSSZ lze stáhnout.")
        return redirect('employee_detail', employee_id=employee.id)

    return render(request, 'employees/employee_cssz_data.html', {'employee': employee, 'form': form})


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_cssz_mark_view(request, employee_id):
    """
    Ruční potvrzení, že přihláška zaměstnance byla odeslána na ČSSZ (datovou schránkou).
    action=sent označí jako nahlášeno, action=undo označení zruší (omylem kliknuto).
    """
    employee = get_object_or_404(Employee, id=employee_id)
    action = request.POST.get('action')

    if action == 'sent':
        employee.is_reported_cssz = True
        employee.reported_cssz_date = timezone.now()
        messages.success(request, f"Přihláška {employee.full_name} na ČSSZ je označená jako odeslaná.")
    elif action == 'undo':
        employee.is_reported_cssz = False
        employee.reported_cssz_date = None
        messages.info(request, f"Označení odeslání na ČSSZ u {employee.full_name} bylo zrušeno.")
    else:
        messages.error(request, "Neznámá akce.")
        return redirect('employee_detail', employee_id=employee.id)

    employee.save(update_fields=['is_reported_cssz', 'reported_cssz_date'])
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_cssz_send_view(request, employee_id):
    """
    Odeslání přihlášky (REGZEC) na ČSSZ přímo z aplikace datovou schránkou (ISDS).
    V testovacím prostředí jde do testovací schránky ČSSZ a zaměstnance neoznačí jako nahlášeného.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    environment = isds_environment()

    if environment == 'prod' and employee.is_reported_cssz:
        messages.warning(request, f"{employee.full_name} už je na ČSSZ nahlášen(a). Podání se znovu neodeslalo.")
        return redirect('employee_detail', employee_id=employee.id)

    try:
        submission = submit_regzec(employee, user=request.user)
    except RegzecDataError as e:
        for problem in e.problems:
            messages.error(request, problem)
        return redirect('employee_detail', employee_id=employee.id)
    except IsdsError as e:
        messages.error(request, f"Odeslání na ČSSZ se nepovedlo: {e}")
        return redirect('employee_detail', employee_id=employee.id)

    if environment == 'prod':
        messages.success(request, f"Přihláška {employee.full_name} odeslána na ČSSZ (datová zpráva {submission.dm_id}). "
                                  "Zaměstnanec je označen jako nahlášený. Protokol od ČSSZ přijde do datové schránky.")
    else:
        messages.success(request, f"TEST: přihláška odeslána do testovací schránky ČSSZ {submission.recipient_box} "
                                  f"(datová zpráva {submission.dm_id}). Za pár minut zkontrolujte odpověď ČSSZ.")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def employee_cssz_protocol_check_view(request, employee_id):
    """Stáhne z datové schránky odpovědi ČSSZ (protokoly) k podáním zaměstnance."""
    employee = get_object_or_404(Employee, id=employee_id)
    try:
        found = check_protocols(employee)
    except IsdsError as e:
        messages.error(request, f"Kontrola odpovědi ČSSZ se nepovedla: {e}")
        return redirect('employee_detail', employee_id=employee.id)

    if found:
        messages.success(request, f"Přijato protokolů od ČSSZ: {found}. Otevřete je v historii podání.")
    else:
        messages.info(request, "ČSSZ zatím neodpověděla. Protokol obvykle přijde do několika minut až hodin, zkuste to později.")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employee_cssz_protocol_view(request, employee_id, submission_id):
    """
    Zobrazí protokol ČSSZ k podání. HTML protokol běží v sandboxu (bez skriptů),
    ?format=xml vrátí strojový protokol, ?format=sent odeslané XML.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    submission = get_object_or_404(employee.cssz_submissions, id=submission_id)
    fmt = request.GET.get('format')

    if fmt == 'sent':
        return HttpResponse(submission.xml_content, content_type='text/plain; charset=utf-8')
    if fmt == 'xml' or (not submission.protocol_html and submission.protocol_xml):
        if not submission.protocol_xml:
            messages.error(request, "K tomuto podání zatím není protokol.")
            return redirect('employee_detail', employee_id=employee.id)
        return HttpResponse(submission.protocol_xml, content_type='text/plain; charset=utf-8')
    if not submission.protocol_html:
        messages.error(request, "K tomuto podání zatím není protokol.")
        return redirect('employee_detail', employee_id=employee.id)

    response = HttpResponse(submission.protocol_html, content_type='text/html; charset=utf-8')
    response['Content-Security-Policy'] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    return response


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def archive_employee_view(request, employee_id):
    """
    Ukončení pracovního poměru: uloží způsob a datum ukončení, vygeneruje výpověď / dohodu
    o ukončení v PDF a přesune zaměstnance do archivu.

    Stránka odesílá formulář přes fetch (hlavička X-Requested-With: fetch) a dostane JSON
    s adresou dokumentu, který otevře v novém okně. Bez JavaScriptu funguje běžné odeslání.
    """
    employee = get_object_or_404(Employee, id=employee_id, is_archived=False)
    form = EmployeeArchiveForm(request.POST or None, employee=employee)
    wants_json = request.headers.get('X-Requested-With') == 'fetch'

    if request.method == 'POST':
        if not form.is_valid():
            if wants_json:
                return JsonResponse({'ok': False}, status=400)
        else:
            employee.is_active = False
            employee.is_archived = True
            employee.termination_type = form.cleaned_data['termination_type']
            employee.termination_notice_date = form.cleaned_data['notice_date']
            employee.termination_date = form.cleaned_data['termination_date']
            employee.termination_reason = form.cleaned_data['termination_reason']
            if employee.user:
                employee.user.is_active = False
                employee.user.save(update_fields=['is_active'])
            employee.save()

            document_url = None
            if has_termination_template(employee.contract_type, employee.termination_type):
                try:
                    store_termination_pdf(employee)
                    document_url = reverse('employee_termination', args=[employee.id])
                except Exception as e:
                    messages.warning(request, f"Poměr byl ukončen, ale dokument se nepodařilo vygenerovat: {e}")

            messages.warning(
                request,
                f"Poměr zaměstnance {employee.full_name} končí dnem {employee.termination_date:%d.%m.%Y}. "
                f"Přesunut do archivu."
            )
            archive_url = reverse('employees_archive_list')
            if wants_json:
                return JsonResponse({'ok': True, 'redirect': archive_url, 'document': document_url})
            return redirect(archive_url)

    context = {
        'employee': employee,
        'form': form,
        'notice_days': NOTICE_PERIOD_DAYS.get(employee.contract_type),
        'has_templates': any(
            has_termination_template(employee.contract_type, key)
            for key, _ in Employee.TERMINATION_TYPE_CHOICES
        ),
    }
    return render(request, 'employees/employee_archive_confirm.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def employees_archive_list_view(request):
    """Samostatný archiv propuštěných a neaktivních zaměstnanců."""
    archived = Employee.objects.filter(is_archived=True).order_by('-termination_date')
    return render(request, 'employees/employees_archive_list.html', {'archived_employees': archived})


@login_required
@role_required([SystemRole.OWNER])
def employee_delete_view(request, employee_id):
    """
    Kompletní a trvalé odstranění zaměstnance z databáze včetně jeho
    navázaného uživatelského účtu Django (User / auth_user), aby se v DB nehromadily sirotčí účty.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    user_to_delete = employee.user
    emp_name = getattr(employee, 'full_name', f"{employee.first_name} {employee.last_name}")

    if request.method == 'POST':
        # Soubory s osobními údaji se nesmažou samy s řádkem v DB
        for pdf in (employee.contract_pdf, employee.termination_pdf):
            if pdf:
                pdf.delete(save=False)
        # Smazáním employee se smaže profil
        employee.delete()
        # Následně smažeme i auth účet uživatele
        if user_to_delete:
            user_to_delete.delete()

        messages.success(request, f"Zaměstnanec {emp_name} i jeho uživatelský účet byli trvale odstraněni.")
        return redirect('employee_list')

    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})