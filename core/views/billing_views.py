"""
Fakturační agenda Panther Security: Vystavování vydaných faktur klientům,
Claude OCR přijatých dodavatelských faktur a správa dodavatelů, klientů a objektů.
Přístup k financím má výhradně majitel (SystemRole.OWNER).
"""

from datetime import timedelta, date, datetime
from decimal import Decimal
import os
import urllib.parse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import models
from django.http import Http404
from django.core.files.base import ContentFile

from core.decorators import role_required
from core.models import (
    Invoice,
    InvoiceItem,
    InvoiceType,
    InvoiceStatus,
    Supplier,
    SystemRole,
    Client,
    GuardObject,
    ContactPerson,
)
from core.forms import (
    GenerateClientInvoiceForm,
    IncomingInvoiceForm,
    InvoiceUploadForm,
    SupplierForm,
    ClientCreateForm,
    ClientUpdateForm,
    GuardObjectCreateForm,
    GuardObjectUpdateForm,
    ContactPersonForm,
)
from core.services import extract_data_from_invoice


def _format_iban(account_number_str, bank_code_str):
    """Základní formátování CZ IBAN pro platební standard SPAYD."""
    clean_acc = str(account_number_str).replace(" ", "").replace("-", "")
    if clean_acc.startswith("CZ"):
        return clean_acc

    bank_code = str(bank_code_str).strip() or "0800"
    account = str(account_number_str).strip() or "123456789"

    prefix = "0"
    acc_body = account
    if "-" in account:
        parts = account.split("-")
        prefix = parts[0]
        acc_body = parts[1]

    try:
        prefix_num = f"{int(prefix):06d}"
        body_num = f"{int(acc_body):010d}"
        code_num = f"{int(bank_code):04d}"
        numeric_iban = f"{code_num}{prefix_num}{body_num}123500"
        checksum = 98 - (int(numeric_iban) % 97)
        return f"CZ{checksum:02d}{code_num}{prefix_num}{body_num}"
    except Exception:
        return "CZ6508000000000123456789"


def _format_price(val):
    """Zformátuje číslo/Decimal na český formát s mezerami (např. 125 400,00)."""
    try:
        d = Decimal(str(val))
        return f"{d:,.2f}".replace(",", " ").replace(".", ",")
    except Exception:
        return str(val)


@login_required
@role_required([SystemRole.OWNER])
def invoice_list_view(request):
    """
    Přehled fakturace pouze pro majitele s volbou období (měsíc / celý rok / vše)
    a přepočtem celkových tržeb, nákladů a bilance.
    """
    now = timezone.now()
    year_param = request.GET.get('year', str(now.year))
    month_param = request.GET.get('month', str(now.month))

    outgoing_qs = Invoice.objects.filter(invoice_type=InvoiceType.OUTGOING).select_related('client')
    incoming_qs = Invoice.objects.filter(invoice_type=InvoiceType.INCOMING).select_related('supplier')

    # Filtrování podle roku
    selected_year = None
    if year_param != 'all':
        try:
            selected_year = int(year_param)
            outgoing_qs = outgoing_qs.filter(issue_date__year=selected_year)
            incoming_qs = incoming_qs.filter(issue_date__year=selected_year)
        except ValueError:
            selected_year = now.year
            year_param = str(selected_year)

    # Filtrování podle měsíce
    selected_month = None
    if month_param != 'all':
        try:
            selected_month = int(month_param)
            outgoing_qs = outgoing_qs.filter(issue_date__month=selected_month)
            incoming_qs = incoming_qs.filter(issue_date__month=selected_month)
        except ValueError:
            selected_month = now.month
            month_param = str(selected_month)

    outgoing = list(outgoing_qs.order_by('-issue_date', '-id'))
    incoming = list(incoming_qs.order_by('-issue_date', '-id'))

    sum_outgoing = sum(i.total_amount for i in outgoing)
    sum_incoming = sum(i.total_amount for i in incoming)
    sum_profit = sum_outgoing - sum_incoming

    # Výpočet pro šipky předchozí / další měsíc
    if selected_year and selected_month:
        try:
            curr_dt = date(selected_year, selected_month, 1)
            prev_dt = (curr_dt - timedelta(days=1)).replace(day=1)
            next_dt = (curr_dt + timedelta(days=32)).replace(day=1)
            prev_year, prev_month = prev_dt.year, prev_dt.month
            next_year, next_month = next_dt.year, next_dt.month
        except Exception:
            prev_year, prev_month = now.year, now.month
            next_year, next_month = now.year, now.month
    else:
        prev_year, prev_month = now.year, now.month
        next_year, next_month = now.year, now.month

    months_list = [
        (1, 'Leden'), (2, 'Únor'), (3, 'Březen'), (4, 'Duben'),
        (5, 'Květen'), (6, 'Červen'), (7, 'Červenec'), (8, 'Srpen'),
        (9, 'Září'), (10, 'Říjen'), (11, 'Listopad'), (12, 'Prosinec')
    ]
    available_years = list(range(now.year - 2, now.year + 2))

    if year_param == 'all' and month_param == 'all':
        period_title = "Všechna období"
    elif month_param == 'all':
        period_title = f"Celý rok {year_param}"
    else:
        m_name = dict(months_list).get(selected_month, '')
        period_title = f"{m_name} {year_param}"

    # Přidáme bezpečné zjištění stavu po splatnosti
    today = timezone.localdate()
    for inv in outgoing + incoming:
        try:
            inv_due = inv.due_date.date() if isinstance(inv.due_date, datetime) else inv.due_date
            inv.safe_is_overdue = bool(inv.status != InvoiceStatus.PAID and inv_due and inv_due < today)
        except Exception:
            inv.safe_is_overdue = False

    context = {
        'outgoing_invoices': outgoing,
        'incoming_invoices': incoming,
        'total_outgoing': _format_price(sum_outgoing),
        'total_incoming': _format_price(sum_incoming),
        'net_profit': _format_price(sum_profit),
        'is_profit_positive': sum_profit >= 0,
        'year_param': year_param,
        'month_param': month_param,
        'period_title': period_title,
        'months_list': months_list,
        'available_years': available_years,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'is_current_month': (year_param == str(now.year) and month_param == str(now.month)),
        'now': now,
    }
    return render(request, 'billing/invoices_list.html', context)


@login_required
@role_required([SystemRole.OWNER])
def invoice_detail_view(request, variable_symbol):
    """Tiskový a PDF náhled vystaveného daňového dokladu pro klienta (podle VS, čísla i ID)."""
    lookup_filter = models.Q(variable_symbol=variable_symbol) | models.Q(invoice_number=variable_symbol)
    if str(variable_symbol).isdigit():
        lookup_filter |= models.Q(id=int(variable_symbol))

    qs = Invoice.objects.select_related('client').prefetch_related('items').filter(lookup_filter)
    invoice = qs.first()
    if not invoice:
        raise Http404("Faktura nebyla nalezena.")

    bank_account = getattr(settings, 'COMPANY_BANK_ACCOUNT', '352412682/0800')
    bank_code = getattr(settings, 'COMPANY_BANK_CODE', '0800')
    if '/' in bank_account:
        acc_part, bank_code = bank_account.split('/')
    else:
        acc_part = bank_account

    company = {
        'name': getattr(settings, 'COMPANY_NAME', 'Panther Security s.r.o.'),
        'ico': getattr(settings, 'COMPANY_ICO', '22525882'),
        'dic': getattr(settings, 'COMPANY_DIC', 'CZ22525882'),
        'street': getattr(settings, 'COMPANY_STREET', 'Varšavská 715/36'),
        'city': getattr(settings, 'COMPANY_CITY', 'Praha 2'),
        'zip': getattr(settings, 'COMPANY_ZIP', '120 00'),
        'bank_account': bank_account,
        'bank_code': bank_code,
        'iban': _format_iban(acc_part, bank_code),
        'contact_person': 'Lukáš Hejna',
        'contact_role': 'Jednatel společnosti',
        'contact_phone': '+420 608 255 197',
        'email': 'ucto@panther-security.cz',
        'web': 'www.panther-security.cz',
    }

    amount_str = f"{invoice.total_amount:.2f}"
    spayd_parts = [
        "SPD*1.0",
        f"ACC:{company['iban']}",
        f"AM:{amount_str}",
        "CC:CZK",
        f"X-VS:{invoice.variable_symbol or invoice.invoice_number}",
        f"MSG:Faktura {invoice.invoice_number}",
    ]
    spayd_string = "*".join(spayd_parts)
    encoded_spayd = urllib.parse.quote(spayd_string)
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={encoded_spayd}&margin=0"

    formatted_items = []
    for it in invoice.items.all():
        formatted_items.append({
            'description': it.description,
            'quantity': it.quantity,
            'unit_price': _format_price(it.unit_price),
            'total_price': _format_price(it.total_price),
        })

    formatted_totals = {
        'amount_without_vat': _format_price(invoice.amount_without_vat),
        'vat_amount': _format_price(invoice.vat_amount),
        'total_amount': _format_price(invoice.total_amount),
    }

    context = {
        'invoice': invoice,
        'company': company,
        'qr_code_url': qr_code_url,
        'formatted_items': formatted_items,
        'formatted_totals': formatted_totals,
    }
    return render(request, 'billing/invoice_detail.html', context)


@login_required
@role_required([SystemRole.OWNER])
def toggle_invoice_payment_status_view(request, invoice_id):
    """Rychlá změna stavu faktury na Uhrazeno / Neuhrazeno."""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or 'invoice_list'

    if invoice.status == InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.UNPAID
        invoice.paid_date = None
        invoice.save()
        messages.info(request, f"Faktura #{invoice.invoice_number} byla označena jako NEUHRAZENÁ.")
    else:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_date = timezone.localdate()
        invoice.save()
        messages.success(request, f"Faktura #{invoice.invoice_number} byla označena jako UHRAZENÁ ({invoice.paid_date.strftime('%d.%m.%Y')}).")

    return redirect(next_url)


@login_required
@role_required([SystemRole.OWNER])
def generate_client_invoice_view(request):
    """Vystavení nové faktury klientovi."""
    form = GenerateClientInvoiceForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        client = form.cleaned_data['client']
        issue_date = form.cleaned_data['issue_date']
        tax_date = form.cleaned_data['tax_date']
        due_date = form.cleaned_data['due_date']
        notes = form.cleaned_data['notes']

        item_descs = request.POST.getlist('item_description[]')
        item_qtys = request.POST.getlist('item_quantity[]')
        item_prices = request.POST.getlist('item_price[]')

        items_to_create = []
        subtotal = Decimal('0.00')

        for desc, q_str, p_str in zip(item_descs, item_qtys, item_prices):
            if not desc.strip():
                continue
            try:
                qty = Decimal(str(q_str).replace(',', '.'))
                price = Decimal(str(p_str).replace(',', '.'))
                total = round(qty * price, 2)
                subtotal += total
                items_to_create.append({
                    'description': desc.strip(),
                    'quantity': qty,
                    'unit_price': price,
                    'total_price': total
                })
            except (ValueError, TypeError):
                continue

        if not items_to_create:
            messages.error(request, "Zadejte alespoň jednu platnou položku faktury.")
            return render(request, 'billing/invoice_generate.html', {'form': form})

        vat_amount = round(subtotal * Decimal('0.21'), 2)
        total_with_vat = subtotal + vat_amount

        year = issue_date.year
        count = Invoice.objects.filter(invoice_type=InvoiceType.OUTGOING, issue_date__year=year).count() + 1
        inv_number = f"{year}{count:04d}"
        variable_symbol = inv_number

        invoice = Invoice.objects.create(
            invoice_type=InvoiceType.OUTGOING,
            invoice_number=inv_number,
            variable_symbol=variable_symbol,
            client=client,
            amount_without_vat=subtotal,
            vat_rate=21,
            vat_amount=vat_amount,
            total_amount=total_with_vat,
            issue_date=issue_date,
            tax_date=tax_date,
            due_date=due_date,
            notes=notes,
            status=InvoiceStatus.UNPAID,
        )

        for it in items_to_create:
            InvoiceItem.objects.create(invoice=invoice, **it)

        messages.success(request, f"Faktura #{inv_number} byla vystavena.")
        return redirect('invoice_detail', variable_symbol=invoice.variable_symbol)

    return render(request, 'billing/invoice_generate.html', {'form': form})


@login_required
@role_required([SystemRole.OWNER])
def upload_incoming_invoice_view(request):
    """
    Nahrání přijaté faktury:
    - Soubor z kroku 1 se automaticky uloží do session/tempu, takže ho uživatel nemusí nahrávat znovu.
    - Claude AI vytěží data do formuláře.
    - Při uložení se původní doklad automaticky přiřadí do pole document_file.
    """
    upload_form = InvoiceUploadForm()
    invoice_form = IncomingInvoiceForm()
    today = timezone.localdate()

    temp_filename = request.session.get('uploaded_invoice_temp_name', '')
    original_filename = request.session.get('uploaded_invoice_orig_name', '')

    if request.method == 'POST':
        # 1. KROK: ANALÝZA SOUBORU PŘES AI
        if 'scan_invoice' in request.POST:
            upload_form = InvoiceUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                try:
                    uploaded_file = request.FILES['invoice_file']
                    file_content = uploaded_file.read()
                    uploaded_file.seek(0)

                    # Uložíme dočasně soubor do media složky pro automatické připojení
                    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_invoices')
                    os.makedirs(temp_dir, exist_ok=True)
                    safe_name = f"{int(timezone.now().timestamp())}_{uploaded_file.name}"
                    temp_path = os.path.join(temp_dir, safe_name)
                    with open(temp_path, 'wb') as f:
                        f.write(file_content)

                    request.session['uploaded_invoice_temp_name'] = safe_name
                    request.session['uploaded_invoice_orig_name'] = uploaded_file.name
                    temp_filename = safe_name
                    original_filename = uploaded_file.name

                    data = extract_data_from_invoice(uploaded_file)

                    issue_val = data.get('issue_date') or str(today)
                    tax_val = data.get('tax_date') or issue_val
                    due_val = data.get('due_date') or str(today + timedelta(days=14))

                    initial_data = {
                        'supplier_name': data.get('supplier_name', ''),
                        'supplier_ico': data.get('supplier_ico', ''),
                        'supplier_dic': data.get('supplier_dic', ''),
                        'supplier_bank_account': data.get('supplier_bank_account', ''),
                        'invoice_number': data.get('invoice_number', ''),
                        'variable_symbol': data.get('variable_symbol', ''),
                        'issue_date': issue_val,
                        'tax_date': tax_val,
                        'due_date': due_val,
                        'amount_without_vat': data.get('amount_without_vat', 0.0),
                        'vat_rate': data.get('vat_rate', 21),
                        'vat_amount': data.get('vat_amount', 0.0),
                        'total_amount': data.get('total_amount', 0.0),
                        'notes': data.get('notes', ''),
                    }
                    invoice_form = IncomingInvoiceForm(initial=initial_data)
                    messages.info(request, "Doklad byl úspěšně vytěžen přes Claude AI. Zkontrolujte prosím údaje a klikněte na Uložit.")
                except Exception as e:
                    messages.error(request, f"Chyba analýzy faktury: {e}")
            else:
                messages.error(request, "Vyberte prosím platný soubor faktury (PDF, JPG, PNG).")

        # 2. KROK: ULOŽENÍ FAKTURY
        elif 'save_invoice' in request.POST:
            post_data = request.POST.copy()
            if not post_data.get('issue_date'):
                post_data['issue_date'] = str(today)
            if not post_data.get('tax_date'):
                post_data['tax_date'] = post_data.get('issue_date') or str(today)
            if not post_data.get('due_date'):
                post_data['due_date'] = str(today + timedelta(days=14))

            invoice_form = IncomingInvoiceForm(post_data, request.FILES)
            if invoice_form.is_valid():
                inv = invoice_form.save(commit=False)
                inv.invoice_type = InvoiceType.INCOMING
                if not inv.issue_date:
                    inv.issue_date = today
                if not inv.tax_date:
                    inv.tax_date = inv.issue_date
                if not inv.due_date:
                    inv.due_date = today + timedelta(days=14)
                if not inv.invoice_number:
                    year = inv.issue_date.year
                    count = Invoice.objects.filter(invoice_type=InvoiceType.INCOMING, issue_date__year=year).count() + 1
                    inv.invoice_number = f"PF-{year}{count:04d}"

                # 1. Priorita: pokud byl soubor nahrán ručně ve 2. kroku
                if 'document_file' in request.FILES:
                    inv.document_file = request.FILES['document_file']
                # 2. Automatické připojení souboru z 1. kroku (analýzy)
                elif temp_filename:
                    temp_path = os.path.join(settings.MEDIA_ROOT, 'temp_invoices', temp_filename)
                    if os.path.exists(temp_path):
                        with open(temp_path, 'rb') as f:
                            inv.document_file.save(original_filename or temp_filename, ContentFile(f.read()), save=False)
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                        request.session.pop('uploaded_invoice_temp_name', None)
                        request.session.pop('uploaded_invoice_orig_name', None)

                inv.save()
                messages.success(request, f"Přijatá faktura #{inv.invoice_number} byla úspěšně uložena do nákladů i s přiloženým dokumentem.")
                return redirect('invoice_list')
            else:
                errors = []
                for field, errs in invoice_form.errors.items():
                    errors.append(f"{field}: {', '.join(errs)}")
                messages.error(request, f"Formulář obsahuje chyby a nelze jej uložit: {'; '.join(errors)}")

    context = {
        'upload_form': upload_form,
        'invoice_form': invoice_form,
        'original_filename': original_filename,
    }
    return render(request, 'billing/invoice_incoming_upload.html', context)


@login_required
@role_required([SystemRole.OWNER])
def client_list_view(request):
    """Přehled všech evidovaných odběratelů (klientů)."""
    clients = Client.objects.filter(is_active=True).prefetch_related('guard_objects', 'invoices').order_by('name')
    return render(request, 'billing/clients_list.html', {'clients': clients})


@login_required
@role_required([SystemRole.OWNER])
def client_create_view(request):
    """Samostatná stránka se zadáním nového odběratele."""
    form = ClientCreateForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            client = form.save()
            messages.success(request, f"Odběratel {client.name} byl úspěšně zaevidován.")
            return redirect('client_detail', client_id=client.id)
        else:
            messages.error(request, "Zkontrolujte zadané údaje o klientovi.")

    return render(request, 'billing/client_create.html', {'form': form})


@login_required
@role_required([SystemRole.OWNER])
def client_update_view(request, client_id):
    """Úprava údajů klienta."""
    client = get_object_or_404(Client, id=client_id)
    form = ClientUpdateForm(request.POST or None, instance=client)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"Údaje klienta {client.name} byly upraveny.")
        return redirect('client_detail', client_id=client.id)

    return render(request, 'billing/client_update.html', {'client': client, 'form': form})


@login_required
@role_required([SystemRole.OWNER])
def client_detail_view(request, client_id):
    """Karta odběratele s kontaktními osobami, objekty a fakturami."""
    client = get_object_or_404(
        Client.objects.prefetch_related('guard_objects', 'invoices', 'contacts__guard_object'),
        id=client_id
    )
    object_form = GuardObjectCreateForm()
    contact_form = ContactPersonForm(client=client)

    if request.method == 'POST' and 'add_guard_object' in request.POST:
        object_form = GuardObjectCreateForm(request.POST)
        if object_form.is_valid():
            obj = object_form.save(commit=False)
            obj.client = client
            obj.save()
            messages.success(request, f"Stanoviště '{obj.name}' bylo úspěšně přiřazeno klientovi {client.name}.")
            return redirect('client_detail', client_id=client.id)
        else:
            messages.error(request, "Zkontrolujte formulář stanoviště.")

    elif request.method == 'POST' and 'add_contact_person' in request.POST:
        contact_form = ContactPersonForm(request.POST, client=client)
        if contact_form.is_valid():
            contact = contact_form.save(commit=False)
            contact.client = client
            contact.save()
            messages.success(request, f"Kontaktní osoba '{contact.name}' byla uložena.")
            return redirect('client_detail', client_id=client.id)
        else:
            messages.error(request, "Zkontrolujte formulář kontaktní osoby.")

    invoices = client.invoices.filter(invoice_type=InvoiceType.OUTGOING).order_by('-issue_date')

    context = {
        'client': client,
        'guard_objects': client.guard_objects.filter(is_active=True),
        'contacts': client.contacts.select_related('guard_object').all(),
        'invoices': invoices,
        'total_invoiced': sum(inv.total_amount for inv in invoices),
        'object_form': object_form,
        'contact_form': contact_form,
    }
    return render(request, 'billing/client_detail.html', context)


@login_required
@role_required([SystemRole.OWNER])
def guard_object_update_view(request, object_id):
    """Úprava údajů střeženého stanoviště (objektu)."""
    guard_object = get_object_or_404(GuardObject.objects.select_related('client'), id=object_id)
    form = GuardObjectUpdateForm(request.POST or None, instance=guard_object)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"Údaje stanoviště '{guard_object.name}' byly upraveny.")
        return redirect('client_detail', client_id=guard_object.client.id)

    return render(request, 'billing/guard_object_update.html', {'guard_object': guard_object, 'form': form})