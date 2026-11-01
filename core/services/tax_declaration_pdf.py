"""
Vyplnění oficiálního tiskopisu „Prohlášení poplatníka daně z příjmů fyzických osob
ze závislé činnosti“ (MFin 5457, vzor č. 27 – platí pro zdaňovací období 2025 a 2026).

Tiskopis Finanční správy nemá formulářová pole, proto se údaje vepíšou jako vrstva
přes originální PDF. Pozice jsou v pixelech náhledu 1202 × 1700 (převod na body A4 níže).
Podpis a datum doplňuje zaměstnanec ručně – prohlášení je jeho projev vůle.
"""

import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile

from .contract_pdf import _register_fonts

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'documents', 'dane', 'MFin5457_vzor27.pdf')
TEMPLATE_YEARS = {2025, 2026}

PAGE_W, PAGE_H = 595.276, 841.89
_SCALE_X, _SCALE_Y = PAGE_W / 1202, PAGE_H / 1700

# Strana 1 – řádky tabulky dětí (účaří) a sloupce (x vlevo / střed, šířka)
CHILD_ROWS_Y = [1332, 1358, 1384, 1410, 1435]
CREDIT_ROWS_Y = {'basic': 750, 'disability_basic': 848, 'disability_extended': 943, 'ztpp': 1035}


def _pt(x, y):
    return x * _SCALE_X, PAGE_H - y * _SCALE_Y


def _format_birth_number(value):
    digits = ''.join(c for c in str(value or '') if c.isdigit())
    return f"{digits[:6]}/{digits[6:]}" if len(digits) in (9, 10) else (value or '')


class _Writer:
    """Pomocník pro psaní na stránku v souřadnicích náhledu."""

    def __init__(self, canvas, font, bold):
        self.c, self.font, self.bold = canvas, font, bold

    def text(self, x, y, value, size=9, max_width=None):
        value = str(value or '').strip()
        if not value:
            return
        if max_width:
            limit = max_width * _SCALE_X
            while size > 5.5 and self.c.stringWidth(value, self.font, size) > limit:
                size -= 0.5
        self.c.setFont(self.font, size)
        self.c.drawString(*_pt(x, y), value)

    def center(self, x, y, value, size=9):
        value = str(value or '').strip()
        if value:
            self.c.setFont(self.font, size)
            self.c.drawCentredString(*_pt(x, y), value)

    def cross(self, x, y):
        self.c.setFont(self.bold, 13)
        self.c.drawCentredString(*_pt(x, y), 'X')


def build_tax_declaration_pdf(declaration):
    """Vrátí bajty vyplněného tiskopisu pro dané prohlášení."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas

    font, bold = _register_fonts()
    employee = declaration.employee
    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    w = _Writer(c, font, bold)

    # ----- Strana 1 -----
    w.center(985, 162, str(declaration.year), size=12)
    company = getattr(settings, 'COMPANY_NAME', '')
    ico = getattr(settings, 'COMPANY_ICO', '')
    w.text(240, 283, f"{company}, IČO {ico}" if ico else company, max_width=860)
    company_address = ', '.join(p for p in (
        getattr(settings, 'COMPANY_STREET', ''),
        f"{getattr(settings, 'COMPANY_ZIP', '')} {getattr(settings, 'COMPANY_CITY', '')}".strip(),
    ) if p)
    w.text(150, 319, company_address, max_width=950)

    w.text(150, 398, employee.last_name, max_width=290)
    w.text(537, 398, employee.first_name, max_width=225)
    w.text(878, 398, _format_birth_number(employee.birth_number), max_width=225)
    w.text(392, 433, employee.full_address, max_width=715)

    if declaration.basic_credit:
        w.cross(110, CREDIT_ROWS_Y['basic'])
    if declaration.disability == 'BASIC':
        w.cross(110, CREDIT_ROWS_Y['disability_basic'])
    elif declaration.disability == 'EXTENDED':
        w.cross(110, CREDIT_ROWS_Y['disability_extended'])
    if declaration.ztpp:
        w.cross(110, CREDIT_ROWS_Y['ztpp'])

    for child, y in zip(declaration.children.all(), CHILD_ROWS_Y):
        w.text(68, y, child.first_name, size=8.5, max_width=185)
        w.text(266, y, child.last_name, size=8.5, max_width=240)
        w.text(520, y, _format_birth_number(child.birth_number), size=8.5, max_width=130)
        w.center(745, y, f"{child.claim}." if child.claim in '123' else 'N', size=9)
        if child.ztpp:
            w.center(874, y, 'X', size=9)
        if child.adult:
            w.center(961, y, 'X', size=9)
    c.showPage()

    # ----- Strana 2 – bod c) a druhý poplatník -----
    if declaration.other_parent == 'ANO':
        w.cross(912, 188)
        w.text(66, 315, declaration.other_first_name, size=8.5, max_width=185)
        w.text(263, 315, declaration.other_last_name, size=8.5, max_width=225)
        w.text(498, 315, _format_birth_number(declaration.other_birth_number), size=8.5, max_width=150)
        w.text(655, 315, declaration.other_address, size=8, max_width=290)
        w.center(995, 315, declaration.other_claims, size=9)
        w.center(1092, 315, declaration.other_employed, size=9)
        w.text(264, 347, declaration.other_employer_name, size=8.5, max_width=870)
        w.text(264, 375, declaration.other_employer_address, size=8.5, max_width=870)
    elif declaration.other_parent == 'NE':
        w.cross(1013, 188)
    c.showPage()
    c.save()

    overlay = PdfReader(BytesIO(buffer.getvalue()))
    template = PdfReader(TEMPLATE)
    out = PdfWriter()
    for page, layer in zip(template.pages, overlay.pages):
        page.merge_page(layer)
        out.add_page(page)
    out.add_metadata({
        '/Title': f"Prohlášení poplatníka {declaration.year} – {employee.full_name}",
        '/Author': company,
    })
    result = BytesIO()
    out.write(result)
    return result.getvalue()


def store_tax_declaration_pdf(declaration):
    """Vygeneruje tiskopis a uloží ho k prohlášení (starý soubor nahradí)."""
    if declaration.pdf:
        declaration.pdf.delete(save=False)
    declaration.pdf.save(f"prohlaseni_{declaration.year}.pdf", ContentFile(build_tax_declaration_pdf(declaration)), save=True)
