"""
Generování pracovněprávních dokumentů (smlouvy, výpovědi) do PDF ze vzorů ve Wordu.

Vzory jsou v core/documents/*.docx s poli {{nazev_pole}}. Text, tučné písmo
a nadpisy se čtou přímo ze vzoru, takže úprava znění = úprava .docx souboru,
bez zásahu do kódu.

Podporovaná rozvržení vzoru:
- dvousloupcové (smlouva DPP): odstavce před tabulkou = hlavička přes celou šířku,
  tabulka 1×2 = dvousloupcové tělo, vnořená tabulka v těle = podpisy
- jednosloupcové (výpovědi, dohoda o ukončení): odstavce pod sebou,
  tabulka bez vnořené tabulky = podpisy

Do buňky podpisu, která obsahuje slovo „zaměstnavatel“, se vloží firemní razítko.
PDF se kreslí přes ReportLab, takže na serveru není potřeba Word ani LibreOffice.
"""

import os
import re
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'documents')
FONTS_DIR = os.path.join(DOCUMENTS_DIR, 'fonts')

# Typ smlouvy -> vzor smlouvy v core/documents/
CONTRACT_TEMPLATES = {
    'DPP': 'DPP_vzor.docx',
}

# (typ smlouvy, způsob ukončení) -> vzor dokumentu o ukončení
TERMINATION_TEMPLATES = {
    ('DPP', 'EMPLOYER_NOTICE'): 'DPP_vypoved_zamestnavatel.docx',
    ('DPP', 'EMPLOYEE_NOTICE'): 'DPP_vypoved_zamestnanec.docx',
    ('DPP', 'AGREEMENT'): 'DPP_dohoda_o_ukonceni.docx',
}

# Výpovědní doba ve dnech podle typu smlouvy (u DPP § 77 odst. 4 ZP a čl. V. smlouvy)
NOTICE_PERIOD_DAYS = {
    'DPP': 15,
}
NOTICE_TYPES = ('EMPLOYER_NOTICE', 'EMPLOYEE_NOTICE')

EMPTY_VALUE = '.' * 24  # Prázdné pole zůstane k ručnímu doplnění
PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

_W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class ContractTemplateError(Exception):
    """Vzor dokumentu chybí nebo obsahuje pole, které neumíme vyplnit."""


def has_contract_template(contract_type):
    return contract_type in CONTRACT_TEMPLATES


def has_termination_template(contract_type, termination_type):
    return (contract_type, termination_type) in TERMINATION_TEMPLATES


def _template_path(filename):
    return os.path.join(DOCUMENTS_DIR, filename)


def get_template_path(contract_type):
    if not has_contract_template(contract_type):
        raise ContractTemplateError(f"Pro typ smlouvy {contract_type} zatím neexistuje vzor.")
    return _template_path(CONTRACT_TEMPLATES[contract_type])


def compute_termination_date(contract_type, termination_type, notice_date, agreed_end_date=None):
    """
    Den skončení: u výpovědi poslední den výpovědní doby, která začíná dnem doručení
    (doručeno 1. 11. -> 15 dnů -> konec 15. 11.); u dohody a jiného způsobu sjednaný den.
    """
    if termination_type in NOTICE_TYPES and contract_type in NOTICE_PERIOD_DAYS and notice_date:
        return notice_date + timedelta(days=NOTICE_PERIOD_DAYS[contract_type] - 1)
    return agreed_end_date


# ---------------------------------------------------------------------------
# Údaje do dokumentů
# ---------------------------------------------------------------------------

def _fmt_date(value):
    return f"{value.day}. {value.month}. {value.year}" if value else ''


def _fmt_money(value):
    if value is None:
        return ''
    value = Decimal(value)
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(',', ' ')
    return f"{value:,.2f}".replace(',', ' ').replace('.', ',')


def build_contract_context(employee, sign_date, sign_place):
    """Převede kartu zaměstnance na hodnoty pro pole {{...}} ve vzoru."""
    cp, co = (employee.house_number or '').strip(), (employee.orientation_number or '').strip()
    position = getattr(employee, 'position', None)

    return {
        'jmeno': employee.first_name,
        'prijmeni': employee.last_name,
        'datum_narozeni': _fmt_date(employee.birth_date),
        'rodne_cislo': employee.birth_number,
        'trvala_adresa_ulice': employee.street,
        'cislo_popisne': cp,
        'cislo_orientacni': co,
        # Vzor má "{{cislo_popisne}}/{{cislo_orientacni}}" – bez č.o. nechceme viset lomítko
        'cislo_popisne_orientacni': '/'.join(x for x in (cp, co) if x),
        'psc': employee.zip_code,
        'trvala_adresa_mesto': employee.city,
        'pracovni_pozice': position.title if position else 'Strážný',
        'datum_nastupu': _fmt_date(employee.start_employment_date),
        'datum_ukonceni': _fmt_date(employee.contract_end_date),
        'misto_vykonu': employee.work_location,
        'hodinova_mzda': _fmt_money(employee.hourly_rate),
        'misto_podpisu': sign_place,
        'datum_podpisu': _fmt_date(sign_date),
    }


def build_termination_context(employee, sign_place):
    """Údaje smlouvy + údaje o skončení. Podepisuje se v den předání (doručení)."""
    context = build_contract_context(employee, employee.termination_notice_date, sign_place)
    concluded = employee.contract_generated_at
    if concluded is not None:
        from django.utils import timezone
        concluded = timezone.localtime(concluded).date() if timezone.is_aware(concluded) else concluded.date()
    context.update({
        'datum_uzavreni': _fmt_date(concluded or employee.start_employment_date),
        'datum_doruceni': _fmt_date(employee.termination_notice_date),
        'datum_skonceni': _fmt_date(employee.termination_date),
    })
    return context


# ---------------------------------------------------------------------------
# Čtení vzoru
# ---------------------------------------------------------------------------

def _paragraph_markup(paragraph, context, missing):
    """Odstavec z Wordu -> ReportLab markup s tučným písmem a dosazenými poli."""
    parts = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        text = escape(text).replace('\t', ' ').replace('\n', '<br/>')
        parts.append(f'<b>{text}</b>' if run.bold else text)
    markup = ''.join(parts)

    markup = markup.replace('{{cislo_popisne}}/{{cislo_orientacni}}', '{{cislo_popisne_orientacni}}')

    def substitute(match):
        key = match.group(1)
        if key not in context:
            missing.add(f"{{{{{key}}}}}")
            return ''
        value = (str(context[key]) if context[key] is not None else '').strip()
        return escape(value) if value else EMPTY_VALUE

    markup = PLACEHOLDER_RE.sub(substitute, markup)
    if '{{' in markup or '}}' in markup:
        # Pole rozdělené mezi části textu s různým formátováním (např. půlka tučně)
        missing.add('rozdělené pole v odstavci „' + re.sub(r'<[^>]+>', '', markup).strip()[:50] + '…“')
    return re.sub(r' {2,}', ' ', markup).strip()


def _font_size(paragraph, default):
    sizes = [r.font.size.pt for r in paragraph.runs if r.font.size]
    return max(sizes) if sizes else default


def _parse_template(template_path, context):
    """
    Přečte vzor a vrátí (layout, header, body, signatures, blocks):
    - layout 'columns': header + body (dva sloupce) + signatures
    - layout 'single':  blocks = odstavce a podpisové tabulky v pořadí ze vzoru
    """
    from docx import Document
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph

    document = Document(template_path)
    missing = set()

    def para(p, default_size):
        style_name = (p.style.name if p.style is not None else '') or ''
        return {
            'markup': _paragraph_markup(p, context, missing),
            'heading': 1 if style_name == 'Heading 1' else 2 if style_name == 'Heading 2' else 0,
            'center': p.alignment is not None and int(p.alignment) == 1,
            'size': _font_size(p, default_size),
        }

    def signature_cells(table):
        return [[para(p, 8) for p in cell.paragraphs] for cell in table.rows[0].cells]

    header, body, signatures, blocks = [], [], [], []
    layout = 'single'
    for child in document.element.body.iterchildren():
        if child.tag == f'{_W_NS}p':
            p = para(DocxParagraph(child, document), 8)
            header.append(p)
            blocks.append(('p', p))
        elif child.tag == f'{_W_NS}tbl':
            table = DocxTable(child, document)
            has_nested = any(cell._tc.findall(f'{_W_NS}tbl') for cell in table.rows[0].cells)
            if not has_nested:
                blocks.append(('sig', signature_cells(table)))
                continue
            layout = 'columns'
            for cell in table.rows[0].cells:
                for cell_child in cell._tc.iterchildren():
                    if cell_child.tag == f'{_W_NS}p':
                        body.append(para(DocxParagraph(cell_child, cell), 7))
                    elif cell_child.tag == f'{_W_NS}tbl':
                        signatures = signature_cells(DocxTable(cell_child, cell))

    if missing:
        raise ContractTemplateError(
            "Vzor dokumentu obsahuje pole, která nejde vyplnit: " + ', '.join(sorted(missing))
        )
    return layout, header, body, signatures, blocks


# ---------------------------------------------------------------------------
# Vykreslení PDF
# ---------------------------------------------------------------------------

def _register_fonts():
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if 'Montserrat' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Montserrat', os.path.join(FONTS_DIR, 'Montserrat-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Montserrat-Bold', os.path.join(FONTS_DIR, 'Montserrat-Bold.ttf')))
        addMapping('Montserrat', 0, 0, 'Montserrat')
        addMapping('Montserrat', 1, 0, 'Montserrat-Bold')
        addMapping('Montserrat', 0, 1, 'Montserrat')
        addMapping('Montserrat', 1, 1, 'Montserrat-Bold')
    return 'Montserrat', 'Montserrat-Bold'


def _stamp_image(stamp_path, size):
    """Razítko zmenšené na tiskové rozlišení, ať PDF nemá megabajty."""
    from PIL import Image as PILImage
    from reportlab.platypus import Image

    if not stamp_path or not os.path.exists(stamp_path):
        return None
    with PILImage.open(stamp_path) as img:
        img = img.convert('RGBA') if img.mode in ('P', 'LA') else img
        img.thumbnail((600, 600))
        buffer = BytesIO()
        if img.mode == 'RGB':
            img.save(buffer, format='JPEG', quality=88)  # bez průhlednosti -> výrazně menší PDF
        else:
            img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return Image(buffer, width=size, height=size)


def render_contract_pdf(template_path, context, stamp_path=None, title='Smlouva'):
    """Vyplní vzor údaji a vrátí hotové PDF jako bytes."""
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, FrameBreak, KeepTogether, NextPageTemplate, PageTemplate,
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    layout, header, body, signatures, blocks = _parse_template(template_path, context)
    font, font_bold = _register_fonts()
    page_w, page_h = A4
    author = context.get('_company', '')

    def style_for(p, force_center=False, airy=False):
        size = p['size']
        if p['heading'] == 1:
            return ParagraphStyle('h1', fontName=font_bold, fontSize=max(size, 13), leading=max(size, 13) * 1.25,
                                  alignment=TA_CENTER, spaceAfter=2 if airy else 0)
        if p['heading'] == 2:
            return ParagraphStyle('h2', fontName=font_bold, fontSize=size, leading=size * 1.3,
                                  alignment=TA_CENTER, spaceBefore=4, spaceAfter=1.5)
        return ParagraphStyle('p', fontName=font, fontSize=size,
                              leading=size * (1.45 if airy else 1.26),
                              alignment=TA_CENTER if (p['center'] or force_center) else TA_LEFT,
                              spaceAfter=size * (0.7 if airy else 0.2))

    def flowables(paragraphs, force_center=False, airy=False):
        return [Paragraph(p['markup'], style_for(p, force_center, airy)) for p in paragraphs if p['markup']]

    def signature_table(cells, width, stamp_size):
        stamp = _stamp_image(stamp_path, stamp_size)
        rows = []
        for cell in cells:
            items = flowables(cell, force_center=True)
            is_employer = any('zaměstnavatel' in p['markup'].lower() for p in cell)
            top = stamp if (is_employer and stamp) else Spacer(1, stamp_size)
            rows.append([top] + items)
        table = Table([rows], colWidths=[width / len(rows)] * len(rows))
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return table

    buffer = BytesIO()

    # --- Jednosloupcový dokument (výpověď, dohoda o ukončení) ----------------
    if layout == 'single':
        margin = 20 * mm
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margin, rightMargin=margin,
                                topMargin=18 * mm, bottomMargin=18 * mm, title=title, author=author)
        story = []
        for kind, item in blocks:
            if kind == 'p':
                story.extend(flowables([item], airy=True))
            else:
                # Místo a datum podpisu drží pohromadě s podpisy
                tail = [story.pop()] if story else []
                sig = signature_table(item, page_w - 2 * margin, 30 * mm)
                story.append(KeepTogether(tail + [Spacer(1, 6 * mm), sig]))
        doc.build(story)
        return buffer.getvalue()

    # --- Dvousloupcový dokument (smlouva) ------------------------------------
    margin_x, margin_y = 12 * mm, 10 * mm
    content_w = page_w - 2 * margin_x
    column_gap = 6 * mm
    column_width = (content_w - column_gap) / 2
    body_flowables = flowables(body)

    # Podpisy jsou ve vzoru vnořené na konci pravého sloupce – zachováme to
    if signatures:
        sig = signature_table(signatures, column_width - 4 * mm, 26 * mm)
        tail = [body_flowables.pop()] if body_flowables else []
        body_flowables.append(KeepTogether(tail + [Spacer(1, 2 * mm), sig]))

    # Hlavička přes celou šířku, pod ní dva sloupce. Výška hlavičky se změří
    # předem, aby sloupce začínaly přesně pod ní (jméno může mít víc řádků).
    header_flowables = flowables(header) + [Spacer(1, 3 * mm)]
    header_h = sum(
        f.wrap(content_w, page_h)[1] + f.getSpaceBefore() + f.getSpaceAfter()
        for f in header_flowables
    ) + 4

    def columns(top_y):
        col_h = top_y - margin_y
        return [
            Frame(margin_x, margin_y, column_width, col_h, id='left', showBoundary=0,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
            Frame(margin_x + column_width + column_gap, margin_y, column_width, col_h, id='right',
                  showBoundary=0, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
        ]

    first_top = page_h - margin_y
    header_frame = Frame(margin_x, first_top - header_h, content_w, header_h, id='header',
                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(buffer, pagesize=A4, title=title, author=author)
    doc.addPageTemplates([
        PageTemplate(id='first', frames=[header_frame] + columns(first_top - header_h)),
        PageTemplate(id='next', frames=columns(first_top)),
    ])

    story = header_flowables + [NextPageTemplate('next'), FrameBreak()] + body_flowables
    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Vstup z aplikace
# ---------------------------------------------------------------------------

def _stamp_path():
    from django.conf import settings
    return os.path.join(settings.BASE_DIR, 'static', 'images', 'stamp_signature.png')


def _sign_place():
    from django.conf import settings
    return getattr(settings, 'CONTRACT_SIGN_PLACE', 'Praze')


def _company():
    from django.conf import settings
    return getattr(settings, 'COMPANY_NAME', '')


def generate_contract_pdf(employee, sign_date=None):
    """Vygeneruje smlouvu pro zaměstnance podle jeho typu smlouvy. Vrací bytes PDF."""
    from django.utils import timezone

    context = build_contract_context(employee, sign_date or timezone.localdate(), _sign_place())
    context['_company'] = _company()
    return render_contract_pdf(
        get_template_path(employee.contract_type),
        context,
        stamp_path=_stamp_path(),
        title=f"{employee.contract_type} – {employee.first_name} {employee.last_name}",
    )


def generate_termination_pdf(employee):
    """Vygeneruje dokument o skončení podle typu smlouvy a způsobu ukončení. Vrací bytes PDF."""
    key = (employee.contract_type, employee.termination_type)
    if key not in TERMINATION_TEMPLATES:
        raise ContractTemplateError(
            f"Pro {employee.contract_type} a způsob ukončení „{employee.get_termination_type_display()}“ "
            f"zatím neexistuje vzor dokumentu."
        )
    context = build_termination_context(employee, _sign_place())
    context['_company'] = _company()
    return render_contract_pdf(
        _template_path(TERMINATION_TEMPLATES[key]),
        context,
        stamp_path=_stamp_path(),
        title=f"{employee.get_termination_type_display()} – {employee.first_name} {employee.last_name}",
    )


def _store_pdf(employee, file_field, timestamp_field, pdf_bytes, name):
    """Uloží PDF do souborového pole zaměstnance a smaže případnou starší verzi."""
    from django.core.files.base import ContentFile
    from django.utils import timezone

    field = getattr(employee, file_field)
    if field:
        field.delete(save=False)
    field.save(name, ContentFile(pdf_bytes), save=False)
    setattr(employee, timestamp_field, timezone.now())
    employee.save(update_fields=[file_field, timestamp_field])
    return getattr(employee, file_field)


def store_contract_pdf(employee):
    """
    Vygeneruje smlouvu, uloží ji na kartu zaměstnance a smaže případnou starší verzi.
    Výjimky propouští dál – volající rozhoduje, jak je zobrazit.
    """
    pdf_bytes = generate_contract_pdf(employee)
    return _store_pdf(employee, 'contract_pdf', 'contract_generated_at', pdf_bytes,
                      f"{employee.contract_type}.pdf")


def store_termination_pdf(employee):
    """Vygeneruje dokument o skončení (výpověď / dohodu) a uloží ho na kartu zaměstnance."""
    pdf_bytes = generate_termination_pdf(employee)
    return _store_pdf(employee, 'termination_pdf', 'termination_generated_at', pdf_bytes,
                      "ukonceni.pdf")