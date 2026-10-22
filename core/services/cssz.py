"""
Generátor oficiálního XML hlášení ČSSZ (ONZ2022 - Oznámení o nástupu do zaměstnání).
"""

from xml.etree.ElementTree import Element, SubElement, tostring
from django.conf import settings
from django.utils import timezone
from core.models import Employee


def generate_onz_xml(employee: Employee) -> str:
    """
    Sestaví validní XML balíček dle oficiálního XSD schématu ČSSZ (typ ONZ2022)
    s údaji firmy Panther Security a nového zaměstnance.
    """
    company_ico = getattr(settings, 'COMPANY_ICO', '22525882')
    company_vs = getattr(settings, 'COMPANY_CSSZ_VS', '8862067306')
    company_name = getattr(settings, 'COMPANY_NAME', 'Panther Security s.r.o.')

    root = Element('onz', {
        'xmlns': '[http://schemas.cssz.cz/ONZ/2022](http://schemas.cssz.cz/ONZ/2022)',
        'verze': '2022.1'
    })

    # Hlavička podání
    header = SubElement(root, 'hlavicka')
    SubElement(header, 'typPodani').text = 'ONZ'
    SubElement(header, 'datumPodani').text = timezone.now().strftime('%Y-%m-%d')
    SubElement(header, 'kodOkresu').text = getattr(settings, 'COMPANY_CSSZ_DEP', '886')

    # Identifikace zaměstnavatele
    employer = SubElement(root, 'zamestnavatel')
    SubElement(employer, 'ico').text = str(company_ico)
    SubElement(employer, 'variabilniSymbol').text = str(company_vs)
    SubElement(employer, 'nazev').text = company_name

    # Údaje o pojištěnci (zaměstnanci)
    insured = SubElement(root, 'pojistenec')
    SubElement(insured, 'typAkce').text = '1'  # 1 = Nástup do zaměstnání
    SubElement(insured, 'jmeno').text = employee.first_name
    SubElement(insured, 'prijmeni').text = employee.last_name

    # Očištěné rodné číslo bez lomítka
    clean_rc = employee.birth_number.replace('/', '').strip() if employee.birth_number else ''
    SubElement(insured, 'rodneCislo').text = clean_rc

    if employee.birth_date:
        SubElement(insured, 'datumNarozeni').text = employee.birth_date.strftime('%Y-%m-%d')

    # Trvalé bydliště
    addr = SubElement(insured, 'adresaTrvala')
    SubElement(addr, 'ulice').text = employee.street or employee.city
    SubElement(addr, 'cisloPopisne').text = employee.house_number or ''
    SubElement(addr, 'cisloOrientacni').text = employee.orientation_number or ''
    SubElement(addr, 'obec').text = employee.city
    SubElement(addr, 'psc').text = employee.zip_code.replace(' ', '')
    SubElement(addr, 'stat').text = 'CZE'

    # Pracovní poměr & ČSSZ parametry
    employment = SubElement(root, 'pracovniPomer')
    SubElement(employment, 'datumNastupu').text = employee.start_employment_date.strftime('%Y-%m-%d')
    SubElement(employment, 'druhCinnosti').text = '1' if employee.contract_type == 'HPP' else 'T'
    SubElement(employment, 'zdravotniPojistovna').text = employee.health_insurance_code

    return tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')