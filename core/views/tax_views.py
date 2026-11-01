"""
Prohlášení poplatníka daně („růžový papír“): předvyplnění oficiálního tiskopisu,
evidence podpisu a odvolání. Podepsané prohlášení se promítá do výpočtu mezd.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import role_required
from core.forms.tax_forms import (
    TaxDeclarationChildFormSet,
    TaxDeclarationForm,
    TaxDeclarationSignForm,
    TaxDeclarationWithdrawForm,
)
from core.models import Employee, SystemRole, TaxDeclaration
from core.private_files import serve_private_file
from core.services.tax_declaration_pdf import TEMPLATE_YEARS, store_tax_declaration_pdf


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def tax_declaration_edit_view(request, employee_id):
    """
    Vyplnění prohlášení na zdaňovací období (?year=, výchozí letošní). Podepsané
    prohlášení už měnit nejde – změna se řeší odvoláním a novým prohlášením.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    year = int(request.GET.get('year') or timezone.localdate().year)
    if year not in TEMPLATE_YEARS:
        messages.error(request, f"Pro rok {year} zatím aplikace nemá platný tiskopis prohlášení (vzor č. 27 platí pro {', '.join(map(str, sorted(TEMPLATE_YEARS)))}).")
        return redirect('employee_detail', employee_id=employee.id)
    if not employee.birth_number or not employee.full_address:
        messages.error(request, "Na kartě zaměstnance chybí rodné číslo nebo adresa trvalého pobytu – doplňte je přes „Doplnit údaje pro ČSSZ“.")
        return redirect('employee_detail', employee_id=employee.id)

    declaration = TaxDeclaration.current_for(employee, year)
    if declaration and declaration.signed_on:
        messages.warning(request, "Podepsané prohlášení už nejde upravit. Pro změnu ho odvolejte a vyplňte nové.")
        return redirect('employee_detail', employee_id=employee.id)
    declaration = declaration or TaxDeclaration(employee=employee, year=year)

    form = TaxDeclarationForm(request.POST or None, instance=declaration)
    children = TaxDeclarationChildFormSet(request.POST or None, instance=declaration, prefix='children')

    if request.method == 'POST':
        valid = form.is_valid() and children.is_valid()
        if valid:
            claimed = [
                f.cleaned_data for f in children.forms
                if f.cleaned_data and not f.cleaned_data.get('DELETE') and f.cleaned_data.get('claim') in ('1', '2', '3')
            ]
            form.check_other_parent(bool(claimed))
            valid = not form.errors
        if valid:
            with transaction.atomic():
                declaration = form.save()
                children.instance = declaration
                children.save()
                store_tax_declaration_pdf(declaration)
            messages.success(request, "Prohlášení je vyplněné. Vytiskněte ho, nechte zaměstnance podepsat a podpis zaznamenejte na kartě.")
            return redirect('employee_detail', employee_id=employee.id)
        messages.error(request, "Zkontrolujte zvýrazněné údaje.")

    return render(request, 'employees/tax_declaration_form.html', {
        'employee': employee, 'year': year, 'form': form, 'children': children,
    })


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def tax_declaration_pdf_view(request, employee_id, declaration_id):
    """Vyplněný tiskopis (?scan=1 podepsaný sken) – obsahuje rodná čísla, jen přes kontrolu role."""
    declaration = get_object_or_404(TaxDeclaration, id=declaration_id, employee_id=employee_id)
    if request.GET.get('scan'):
        return serve_private_file(declaration.signed_scan)
    if not declaration.pdf:
        raise Http404("Tiskopis zatím není vygenerovaný.")
    name = f"Prohlaseni_poplatnika_{declaration.year}_{declaration.employee.personal_number or declaration.employee_id}.pdf"
    return serve_private_file(declaration.pdf, download_name=name)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def tax_declaration_sign_view(request, employee_id, declaration_id):
    """Zaměstnanec prohlášení podepsal – od toho měsíce se uplatní slevy ve mzdě."""
    declaration = get_object_or_404(TaxDeclaration, id=declaration_id, employee_id=employee_id, withdrawn_on__isnull=True)
    form = TaxDeclarationSignForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Zadejte datum podpisu.")
    elif form.cleaned_data['signed_on'].year != declaration.year:
        messages.error(request, f"Prohlášení na rok {declaration.year} musí být podepsané v tomto roce.")
    elif form.cleaned_data['signed_on'] > timezone.localdate():
        messages.error(request, "Datum podpisu nemůže být v budoucnosti.")
    else:
        declaration.signed_on = form.cleaned_data['signed_on']
        if form.cleaned_data.get('signed_scan'):
            declaration.signed_scan = form.cleaned_data['signed_scan']
        declaration.save()
        messages.success(request, f"Podpis prohlášení zaznamenán ({declaration.signed_on:%d.%m.%Y}). "
                                  f"Slevy na dani se uplatní ve mzdě od {declaration.signed_on:%m/%Y}.")
    return redirect('employee_detail', employee_id=employee_id)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
@require_POST
def tax_declaration_withdraw_view(request, employee_id, declaration_id):
    """Odvolání prohlášení (zaměstnanec podepsal u jiného plátce, změna údajů…)."""
    declaration = get_object_or_404(TaxDeclaration, id=declaration_id, employee_id=employee_id, withdrawn_on__isnull=True)
    form = TaxDeclarationWithdrawForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Zadejte datum odvolání.")
        return redirect('employee_detail', employee_id=employee_id)
    declaration.withdrawn_on = form.cleaned_data['withdrawn_on']
    declaration.save(update_fields=['withdrawn_on', 'updated_at'])
    messages.info(request, f"Prohlášení na rok {declaration.year} odvoláno k {declaration.withdrawn_on:%d.%m.%Y}. "
                           "Slevy se přestanou uplatňovat od dalšího měsíce.")
    return redirect('employee_detail', employee_id=employee_id)
