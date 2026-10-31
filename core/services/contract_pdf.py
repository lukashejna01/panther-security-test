"""
Generování pracovních smluv (DPP) do PDF ze vzoru ve Wordu.

Zdrojem znění je soubor core/documents/DPP_vzor.docx s poli {{nazev_pole}}.
Text, tučné písmo a nadpisy se čtou přímo ze vzoru, takže úprava znění
smlouvy = úprava .docx souboru, bez zásahu do kódu.

Rozvržení vzoru:
- odstavce před tabulkou  -> hlavička přes celou šířku (smluvní strany)
- tabulka 1×2             -> dvousloupcové tělo smlouvy
- vnořená tabulka v těle  -> podpisy; do buňky zaměstnavatele se vloží razítko

PDF se kreslí přes ReportLab (stejně jako výdajové doklady), takže na serveru
není potřeba Word ani LibreOffice.
"""

import os
import re
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'documents')
FONTS_DIR = os.path.join(DOCUMENTS_DIR, 'fonts')

# Typ smlouvy -> soubor vzoru v core/documents/
CONTRACT_TEMPLATES = {
    'DPP': 'DPP_vzor.docx',
}

EMPTY_VALUE = '.' * 24  # Prázdné pole zůstane k ručnímu doplnění
PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

_W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class ContractTemplateError(Exception):
    """Vzor smlouvy chybí nebo obsahuje pole, které neumíme vyplnit."""


def has_contract_template(contract_type):
    return contract_type in CONTRACT_TEMPLATES


def get_template_path(contract_type):
    if not has_contract_template(contract_type):
        raise ContractTemplateError(f"Pro typ smlouvy {contract_type} zatím neexistuje vzor.")
    return os.path.join(DOCUMENTS_DIR, CONTRACT_TEMPLATES[contract_type])


# ---------------------------------------------------------------------------
# Údaje do smlouvy
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
    """Rozdělí vzor na hlavičku, tělo a podpisové buňky (vše jako surová data)."""
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

    header, body, signatures = [], [], []
    for child in document.element.body.iterchildren():
        if child.tag == f'{_W_NS}p':
            header.append(para(DocxParagraph(child, document), 8))
        elif child.tag == f'{_W_NS}tbl':
            table = DocxTable(child, document)
            for cell in table.rows[0].cells:
                for cell_child in cell._tc.iterchildren():
                    if cell_child.tag == f'{_W_NS}p':
                        body.append(para(DocxParagraph(cell_child, cell), 7))
                    elif cell_child.tag == f'{_W_NS}tbl':
                        sig_table = DocxTable(cell_child, cell)
                        for sig_cell in sig_table.rows[0].cells:
                            signatures.append([para(p, 7) for p in sig_cell.paragraphs])

    if missing:
        raise ContractTemplateError(
            "Vzor smlouvy obsahuje pole, která nejde vyplnit: " + ', '.join(sorted(missing))
        )
    return header, body, signatures


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
        Paragraph, Spacer, Table, TableStyle,
    )

    header, body, signatures = _parse_template(template_path, context)
    font, font_bold = _register_fonts()

    def style_for(p, force_center=False):
        size = p['size']
        if p['heading'] == 1:
            return ParagraphStyle('h1', fontName=font_bold, fontSize=max(size, 13), leading=max(size, 13) * 1.25,
                                  alignment=TA_CENTER, spaceAfter=0)
        if p['heading'] == 2:
            return ParagraphStyle('h2', fontName=font_bold, fontSize=size, leading=size * 1.3,
                                  alignment=TA_CENTER, spaceBefore=4, spaceAfter=1.5)
        return ParagraphStyle('p', fontName=font, fontSize=size, leading=size * 1.26,
                              alignment=TA_CENTER if (p['center'] or force_center) else TA_LEFT,
                              spaceAfter=size * 0.2)

    def flowables(paragraphs, force_center=False):
        return [Paragraph(p['markup'], style_for(p, force_center)) for p in paragraphs if p['markup']]

    page_w, page_h = A4
    margin_x, margin_y = 12 * mm, 10 * mm
    content_w = page_w - 2 * margin_x
    column_gap = 6 * mm
    column_width = (content_w - column_gap) / 2
    body_flowables = flowables(body)

    # Podpisy jsou ve vzoru vnořené na konci pravého sloupce – zachováme to
    if signatures:
        stamp_size = 26 * mm
        stamp = _stamp_image(stamp_path, stamp_size)
        cells = []
        for cell in signatures:
            items = flowables(cell, force_center=True)
            is_employer = any('zaměstnavatel' in p['markup'].lower() for p in cell)
            top = stamp if (is_employer and stamp) else Spacer(1, stamp_size)
            cells.append([top] + items)
        sig_table = Table([cells], colWidths=[(column_width - 4 * mm) / len(cells)] * len(cells))
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        # Místo a datum podpisu drží pohromadě s podpisy
        tail = [body_flowables.pop()] if body_flowables else []
        body_flowables.append(KeepTogether(tail + [Spacer(1, 2 * mm), sig_table]))

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

    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, title=title, author=context.get('_company', ''))
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

def generate_contract_pdf(employee, sign_date=None):
    """Vygeneruje smlouvu pro zaměstnance podle jeho typu smlouvy. Vrací bytes PDF."""
    from django.conf import settings
    from django.utils import timezone

    stamp_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'stamp_signature.png')
    context = build_contract_context(
        employee,
        sign_date=sign_date or timezone.localdate(),
        sign_place=getattr(settings, 'CONTRACT_SIGN_PLACE', 'Praze'),
    )
    context['_company'] = getattr(settings, 'COMPANY_NAME', '')
    return render_contract_pdf(
        get_template_path(employee.contract_type),
        context,
        stamp_path=stamp_path,
        title=f"{employee.contract_type} – {employee.first_name} {employee.last_name}",
    )


def store_contract_pdf(employee):
    """
    Vygeneruje smlouvu, uloží ji na kartu zaměstnance a smaže případnou starší verzi.
    Vrací uložený soubor. Výjimky propouští dál – volající rozhoduje, jak je zobrazit.
    """
    from django.core.files.base import ContentFile
    from django.utils import timezone

    pdf_bytes = generate_contract_pdf(employee)

    if employee.contract_pdf:
        employee.contract_pdf.delete(save=False)
    employee.contract_pdf.save(f"{employee.contract_type}.pdf", ContentFile(pdf_bytes), save=False)
    employee.contract_generated_at = timezone.now()
    employee.save(update_fields=['contract_pdf', 'contract_generated_at'])
    return employee.contract_pdf