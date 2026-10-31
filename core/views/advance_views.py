"""
Pohledy pro modul záloh na mzdu Panther Security:
- Seznam záloh s filtry a řádkovým přehledem
- Vytvoření zálohy (hotovost s dotykovým podpisem / banka s potvrzením)
- Generování a stažení oficiálního výdajového pokladního dokladu (VPD) v PDF s plnou českou diakritikou a firemním razítkem
"""

import os
import base64
from io import BytesIO
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import role_required
from core.forms import AdvancePaymentForm
from core.models import AdvancePayment, Employee, SystemRole


def _register_czech_font():
    """
    Zaregistruje TrueType font s plnou podporou české diakritiky (UTF-8).
    Prohledává známé cesty na Linuxu / PythonAnywhere i uvnitř ReportLabu.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab

    registered = pdfmetrics.getRegisteredFontNames()
    if "PantherCzech" in registered:
        return "PantherCzech", "PantherCzech-Bold" if "PantherCzech-Bold" in registered else "PantherCzech"

    font_candidates_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        os.path.join(os.path.dirname(reportlab.__file__), "fonts", "DejaVuSans.ttf"),
    ]

    font_candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        os.path.join(os.path.dirname(reportlab.__file__), "fonts", "DejaVuSans-Bold.ttf"),
    ]

    reg_name = None
    bold_name = None

    for p in font_candidates_regular:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("PantherCzech", p))
                reg_name = "PantherCzech"
                break
            except Exception:
                pass

    for p in font_candidates_bold:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("PantherCzech-Bold", p))
                bold_name = "PantherCzech-Bold"
                break
            except Exception:
                pass

    if not reg_name:
        return "Helvetica", "Helvetica-Bold"

    return reg_name, (bold_name or reg_name)


def _generate_vpd_pdf(advance: AdvancePayment) -> bytes:
    """Vygeneruje PDF výdajový pokladní doklad přes ReportLab s plnou podporou české diakritiky a razítkem."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    font_name, font_bold = _register_czech_font()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName=font_bold,
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#0f172a'),
        alignment=1,
        spaceAfter=15
    )
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    bold_style = ParagraphStyle(
        'BoldStyle',
        parent=styles['Normal'],
        fontName=font_bold,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )

    elements = []

    # 1. Název dokladu
    doc_num = f"VPD-{advance.created_at.strftime('%Y')}-{advance.id:04d}"
    elements.append(Paragraph(f"VÝDAJOVÝ POKLADNÍ DOKLAD č. {doc_num}", title_style))
    elements.append(Spacer(1, 10))

    # 2. Informace o stranách
    addr = getattr(advance.employee, 'full_address', '') or 'Neuvedeno'
    emp_name = advance.employee.full_name
    birth_info = advance.employee.birth_number or (advance.employee.birth_date.strftime('%d.%m.%Y') if advance.employee.birth_date else 'Neuvedeno')

    company_data = [
        [
            Paragraph("<b>Plátce (Zaměstnavatel):</b><br/>"
                      "<b>Panther Security s.r.o.</b><br/>"
                      "Varšavská 715/36, Praha 2, 120 00<br/>"
                      "IČO: 22525882 | DIČ: CZ22525882", header_style),
            Paragraph("<b>Příjemce (Zaměstnanec):</b><br/>"
                      f"<b>{emp_name}</b><br/>"
                      f"Os. číslo: {advance.employee.personal_number or 'Neuvedeno'}<br/>"
                      f"RČ / Datum nar.: {birth_info}<br/>"
                      f"Bydliště: {addr}", header_style)
        ]
    ]
    t_parties = Table(company_data, colWidths=[260, 260])
    t_parties.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(t_parties)
    elements.append(Spacer(1, 15))

    # 3. Podrobnosti o vyplacené částce
    note_txt = advance.note or 'Bez doplňující poznámky'
    amount_czk = f"{advance.amount:,.2f} Kč".replace(',', ' ')

    details_data = [
        [Paragraph("Účel platby:", bold_style), Paragraph(f"Záloha na mzdu – {note_txt}", header_style)],
        [Paragraph("Forma úhrady:", bold_style), Paragraph("Hotovostní výdej z pokladny", header_style)],
        [Paragraph("Datum a čas vystavení:", bold_style), Paragraph(advance.created_at.strftime("%d.%m.%Y v %H:%M"), header_style)],
        [Paragraph("Částka k výplatě:", ParagraphStyle('BigSum', parent=bold_style, fontSize=11, textColor=colors.HexColor('#0f766e'))), 
         Paragraph(f"<b>{amount_czk}</b>", ParagraphStyle('BigSumVal', parent=bold_style, fontName=font_bold, fontSize=12, textColor=colors.HexColor('#0f766e')))]
    ]
    t_details = Table(details_data, colWidths=[150, 370])
    t_details.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t_details)
    elements.append(Spacer(1, 25))

    # 4. Sekce pro podpisy
    # Razítko s podpisem majitele (zaměstnavatel)
    company_stamp = None
    stamp_paths = [
        os.path.join(settings.BASE_DIR, 'static', 'images', 'stamp_signature.png'),
        os.path.join(settings.STATIC_ROOT or '', 'images', 'stamp_signature.png'),
        os.path.join(settings.BASE_DIR, 'media', 'company', 'stamp_signature.png'),
        os.path.join(settings.BASE_DIR, 'core', 'static', 'images', 'stamp_signature.png'),
    ]
    for sp in stamp_paths:
        if sp and os.path.exists(sp):
            try:
                # Rozměr razítka optimalizovaný pro tiskový doklad
                company_stamp = RLImage(sp, width=110, height=110)
                break
            except Exception:
                pass

    # Podpis zaměstnance z canvasu
    sig_image = None
    if advance.signature_data and advance.signature_data.startswith('data:image'):
        try:
            format_part, img_str = advance.signature_data.split(';base64,')
            img_data = base64.b64decode(img_str)
            sig_buffer = BytesIO(img_data)
            sig_image = RLImage(sig_buffer, width=140, height=55)
        except Exception:
            sig_image = None

    employer_cell = [
        Paragraph("<b>Vyplatil (Za zaměstnavatele):</b>", header_style),
    ]
    if company_stamp:
        employer_cell.append(Spacer(1, 4))
        employer_cell.append(company_stamp)
    else:
        employer_cell.append(Paragraph("<br/><br/><br/>.......................................................<br/>Podpis a razítko", header_style))

    sign_data = [
        [
            employer_cell,
            [
                Paragraph("<b>Převzal v hotovosti (Příjemce):</b>", header_style),
                sig_image if sig_image else Paragraph("<br/><br/>.......................................................<br/>Vlastnoruční podpis", header_style),
                Paragraph(f"<font size=7 color='#64748b'>Elektronicky podepsáno dne {advance.created_at.strftime('%d.%m.%Y %H:%M')}</font>", header_style)
            ]
        ]
    ]
    t_signs = Table(sign_data, colWidths=[260, 260])
    t_signs.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(t_signs)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def advance_list_view(request):
    """
    Globální přehled všech vystavených záloh.
    Podpora filtrování podle vybraného měsíce, roku, zaměstnance a platební metody.
    """
    now = timezone.now()
    advances_qs = AdvancePayment.objects.select_related('employee', 'issued_by').all()

    employee_id = request.GET.get('employee_id', '')
    payment_method = request.GET.get('payment_method', '')
    month_val = request.GET.get('month', str(now.month))
    year_val = request.GET.get('year', str(now.year))

    selected_year = None
    if year_val != 'all':
        try:
            selected_year = int(year_val)
            advances_qs = advances_qs.filter(created_at__year=selected_year)
        except ValueError:
            selected_year = now.year
            year_val = str(selected_year)

    selected_month = None
    if month_val != 'all':
        try:
            selected_month = int(month_val)
            advances_qs = advances_qs.filter(created_at__month=selected_month)
        except ValueError:
            selected_month = now.month
            month_val = str(selected_month)

    if employee_id and employee_id.isdigit():
        advances_qs = advances_qs.filter(employee_id=int(employee_id))

    if payment_method in ['CASH', 'BANK']:
        advances_qs = advances_qs.filter(payment_method=payment_method)

    advances = list(advances_qs.order_by('-created_at'))
    total_amount = sum(a.amount for a in advances)
    total_cash = sum(a.amount for a in advances if a.payment_method == 'CASH')
    total_bank = sum(a.amount for a in advances if a.payment_method == 'BANK')

    months_list = [
        (1, 'Leden'), (2, 'Únor'), (3, 'Březen'), (4, 'Duben'),
        (5, 'Květen'), (6, 'Červen'), (7, 'Červenec'), (8, 'Srpen'),
        (9, 'Září'), (10, 'Říjen'), (11, 'Listopad'), (12, 'Prosinec')
    ]
    available_years = list(range(now.year - 2, now.year + 3))
    employees = Employee.objects.filter(is_active=True).order_by('last_name', 'first_name')

    context = {
        'advances': advances,
        'total_amount': total_amount,
        'total_cash': total_cash,
        'total_bank': total_bank,
        'employees': employees,
        'months_list': months_list,
        'available_years': available_years,
        'selected_employee': employee_id,
        'selected_method': payment_method,
        'selected_month': month_val,
        'selected_year': year_val,
        'now': now,
    }
    return render(request, 'advances/advance_list.html', context)


@login_required
@role_required([SystemRole.MANAGER, SystemRole.OWNER])
def advance_create_view(request, employee_id=None):
    """
    Vystavení nové zálohy manažerem.
    Při hotovosti automaticky vygeneruje podepsané PDF VPD.
    """
    employee = None
    if employee_id:
        employee = get_object_or_404(Employee, id=employee_id)

    if request.method == 'POST':
        form = AdvancePaymentForm(request.POST, request.FILES, employee_id=employee_id)
        if form.is_valid():
            advance = form.save(commit=False)
            if employee:
                advance.employee = employee
            advance.issued_by = request.user
            advance.save()

            if advance.payment_method == 'CASH':
                try:
                    pdf_bytes = _generate_vpd_pdf(advance)
                    advance.receipt_pdf.save(f"VPD_{advance.id}.pdf", ContentFile(pdf_bytes), save=True)
                except Exception as e:
                    messages.warning(request, f"Záloha byla uložena, ale PDF doklad se nepodařilo vygenerovat: {e}")

            messages.success(
                request,
                f"Záloha ve výši {advance.amount} Kč pro zaměstnance {advance.employee.full_name} byla úspěšně zaevidována."
            )
            return redirect('advance_list')
        else:
            messages.error(request, "Zkontrolujte prosím zadané údaje formuláře.")
    else:
        form = AdvancePaymentForm(employee_id=employee_id)

    context = {
        'form': form,
        'employee': employee,
    }
    return render(request, 'advances/advance_create.html', context)


@login_required
def advance_download_vpd_view(request, advance_id):
    """
    Přímé zobrazení / stažení PDF dokladu o záloze (VPD).
    Vždy generuje doklad čerstvě do paměti s plnou podporou české diakritiky a razítkem.
    """
    advance = get_object_or_404(AdvancePayment.objects.select_related('employee', 'issued_by'), id=advance_id)

    profile = getattr(request.user, 'employee_profile', None)
    is_admin = (
        request.user.is_superuser 
        or request.user.is_staff 
        or (profile and profile.system_role in [SystemRole.MANAGER, SystemRole.OWNER])
    )
    is_own = profile and advance.employee_id == profile.id

    if not (is_admin or is_own):
        messages.error(request, "Nemáte oprávnění k zobrazení tohoto výdajového dokladu.")
        return redirect('advance_list')

    if advance.payment_method == 'BANK':
        if advance.bank_confirmation:
            return redirect(advance.bank_confirmation.url)
        messages.warning(request, "Tato záloha byla vyplacena převodem na účet a nemá VPD doklad.")
        return redirect('advance_list')

    try:
        pdf_bytes = _generate_vpd_pdf(advance)
    except Exception as e:
        messages.error(request, f"Chyba při generování PDF výdajového dokladu: {e}")
        return redirect('advance_list')

    filename = f"VPD_{advance.created_at.strftime('%Y')}_{advance.id:04d}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response