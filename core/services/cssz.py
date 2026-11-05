"""
Registrace zaměstnance na ČSSZ – podání REGZEC (akce 1 = nástup do zaměstnání,
akce 2 = skončení zaměstnání / odhláška).

Od 1. 4. 2026 nahradilo podání REGZEC tiskopis ONZ. Podle data nástupu se použije:
- REGZEC 2025 (namespace .../REGZEC/2025) pro nástupy do 31. 12. 2026,
- REGZEC 2027 (namespace .../REGZEC/2027) pro nástupy od 1. 1. 2027.

Postup: check_regzec_data() vrátí seznam chybějících / chybných údajů srozumitelně česky,
build_regzec_xml() sestaví XML a ověří ho proti oficiálnímu XSD z core/documents/cssz/.
Zdroj pravidel: Definice externí datové věty REGZEC (EDV 1.4.0.7 a 1.5.0.3), ČSSZ/MPSV.
"""

import os
import re
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'documents', 'cssz')

SCHEMAS = {
    2025: {'ns': 'http://schemas.cssz.cz/REGZEC/2025', 'xsd': os.path.join(SCHEMA_DIR, 'REGZEC25', 'REGZEC25.xsd')},
    2027: {'ns': 'http://schemas.cssz.cz/REGZEC/2027', 'xsd': os.path.join(SCHEMA_DIR, 'REGZEC27', 'REGZEC27.xsd')},
}
SCHEMA_2027_FROM = date(2027, 1, 1)
DATA_VERSION = '1.13'           # verze datové věty dle EDV
MAX_DAYS_BEFORE_START = 8       # podání smí předběhnout nástup nejvýš o 8 dní (nástup < datum vyplnění + 9)

# Druh výdělečné činnosti (C_DRCI) – první vztah daného typu u zaměstnavatele
ACTIVITY_CODES = {'HPP': '1', 'DPC': 'A', 'DPP': 'T'}
# Postavení v zaměstnání (CZ-ICSE) – (doba určitá, doba neurčitá)
POSITION_CODES = {'HPP': ('1112', '1111'), 'DPC': ('1212', '1211'), 'DPP': ('1222', '1221')}

_PUNCTUATION = str.maketrans({
    '–': '-', '—': '-', '‑': '-', '„': '"', '“': '"', '”': '"', '‚': "'", '‘': "'", '’': "'",
    ' ': ' ', '…': '...',
})


class RegzecDataError(Exception):
    """Údaje zaměstnance nestačí na podání – obsahuje seznam problémů."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__('; '.join(problems))


def _clean(value):
    """Sjednotí mezery a nahradí typografické znaky, které ČSSZ nepřijímá."""
    return ' '.join(str(value or '').translate(_PUNCTUATION).split())


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def schema_year_for(start_date):
    return 2027 if start_date and start_date >= SCHEMA_2027_FROM else 2025


def _settings():
    from django.conf import settings
    return settings


def _birth_number_ok(rc):
    """Kontrola rodného čísla: délka, u desetimístného dělitelnost 11 (včetně výjimky se zbytkem 10)."""
    if len(rc) == 9:
        return True  # rodná čísla narozených před rokem 1954
    if len(rc) != 10:
        return False
    number = int(rc)
    return number % 11 == 0 or (int(rc[:9]) % 11 == 10 and rc[9] == '0')


def employer_values(test=False):
    s = _settings()
    vs = getattr(s, 'CSSZ_TEST_VS', '') if test else getattr(s, 'COMPANY_CSSZ_VS', '')
    return {
        'vs': _digits(vs),
        'dep': _digits((test and getattr(s, 'CSSZ_TEST_DEP', '')) or getattr(s, 'COMPANY_CSSZ_DEP', '')),
        'name': _clean(getattr(s, 'COMPANY_NAME', '')),
        'profession': _digits(getattr(s, 'CSSZ_PROFESSION_CODE', '')),
        'workmode': _digits(getattr(s, 'CSSZ_WORK_MODE', '3')) or '3',
        'continuous': 'A' if str(getattr(s, 'CSSZ_CONTINUOUS_OPERATION', 'A')).upper().startswith('A') else 'N',
        'municipality': _clean(getattr(s, 'CSSZ_DEFAULT_MUNICIPALITY', '')),
        'municipality_code': _digits(getattr(s, 'CSSZ_DEFAULT_MUNICIPALITY_CODE', '')),
    }


def employer_registered_since():
    """Den registrace firmy jako zaměstnavatele na ČSSZ, nebo None, když není nastavený."""
    value = str(getattr(_settings(), 'COMPANY_CSSZ_EMPLOYER_SINCE', '') or '').strip()
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def check_regzec_data(employee, test=False, today=None):
    """Vrátí seznam problémů, kvůli kterým by ČSSZ podání odmítla. Prázdný seznam = lze podat."""
    from django.utils import timezone

    today = today or timezone.localdate()
    company = employer_values(test)
    problems = []

    # Zaměstnavatel a firemní nastavení
    if len(company['vs']) != 10:
        problems.append("Odesíláte do testovací datovky – nastavte testovací VS od ČSSZ (CSSZ_TEST_VS), skutečný VS testovací ČSSZ nezná." if test
                        else "Variabilní symbol zaměstnavatele musí mít 10 číslic (COMPANY_CSSZ_VS).")
    if len(company['dep']) != 3:
        problems.append("Kód okresní správy sociálního zabezpečení musí mít 3 číslice (COMPANY_CSSZ_DEP).")
    if len(company['profession']) != 5:
        problems.append("V nastavení chybí pětimístný kód profese CZ-ISCO (CSSZ_PROFESSION_CODE).")
    if employee.contract_type not in ACTIVITY_CODES:
        problems.append(f"Typ smlouvy {employee.get_contract_type_display()} se na ČSSZ nehlásí jako zaměstnanec.")

    # Termín
    start = employee.start_employment_date
    if not start:
        problems.append("Chybí datum nástupu.")
    elif (start - today).days > MAX_DAYS_BEFORE_START:
        earliest = start.toordinal() - MAX_DAYS_BEFORE_START
        problems.append(
            f"Podání lze odeslat nejdřív {MAX_DAYS_BEFORE_START} dní před nástupem, "
            f"tedy od {date.fromordinal(earliest):%d.%m.%Y}."
        )
    since = None if test else employer_registered_since()
    if start and since and start < since:
        problems.append(
            f"Firma je u ČSSZ registrovaná jako zaměstnavatel až od {since:%d.%m.%Y}, nástup {start:%d.%m.%Y} "
            "je dřív – ČSSZ by podání zamítla. Opravte datum nástupu, nebo nechte na OSSZ opravit "
            "datum registrace zaměstnavatele (COMPANY_CSSZ_EMPLOYER_SINCE)."
        )

    # Osoba
    if (employee.citizenship or 'CZ').upper() != 'CZ':
        problems.append("Registraci cizince aplikace zatím neumí (pracovní oprávnění, pobyt) – podejte ji přes ePortál ČSSZ.")
    rc = _digits(employee.birth_number)
    if not rc:
        problems.append("Chybí rodné číslo.")
    elif not _birth_number_ok(rc):
        problems.append("Rodné číslo nemá platný formát (kontrola dělitelnosti 11).")
    if not employee.birth_date:
        problems.append("Chybí datum narození.")
    if not employee.sex_from_birth_number:
        problems.append("Z rodného čísla nelze určit pohlaví.")
    for field, label in (('first_name', 'jméno'), ('last_name', 'příjmení'), ('birth_surname', 'rodné příjmení'),
                         ('birth_place', 'místo narození'), ('birth_country', 'stát narození')):
        if not _clean(getattr(employee, field, '')):
            problems.append(f"Chybí {label}.")
    if schema_year_for(start) == 2025 and not employee.education:
        problems.append("Chybí nejvyšší dosažené vzdělání (pro nástupy v roce 2026 je povinné).")

    # Trvalý pobyt
    house = _digits(employee.house_number) or _digits(employee.orientation_number)
    if not house or len(house) > 4:
        problems.append("Číslo popisné trvalého pobytu musí mít 1 až 4 číslice.")
    zip_code = _digits(employee.zip_code)
    if len(zip_code) != 5 or zip_code[0] in '089':
        problems.append("PSČ trvalého pobytu musí mít 5 číslic a nesmí začínat 0, 8 ani 9.")
    if not _clean(employee.city):
        problems.append("Chybí obec trvalého pobytu.")

    # Místo výkonu práce
    municipality = _clean(employee.work_municipality) or company['municipality']
    municipality_code = _digits(employee.work_municipality_code) or company['municipality_code']
    if not municipality:
        problems.append("Chybí obec výkonu práce.")
    if len(municipality_code) != 6:
        problems.append("Kód obce výkonu práce musí mít 6 číslic (např. Praha 554782).")

    return problems


def build_regzec_xml(employee, test=False, today=None):
    """
    Sestaví podání REGZEC (akce 1 – nástup) a ověří ho proti XSD.
    Vrací (xml_bytes, rok_schematu). Při chybějících údajích vyhodí RegzecDataError.
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    problems = check_regzec_data(employee, test=test, today=today)
    if problems:
        raise RegzecDataError(problems)

    company = employer_values(test)
    year = schema_year_for(employee.start_employment_date)
    ns = SCHEMAS[year]['ns']

    def el(parent, tag, **attrs):
        node = SubElement(parent, tag)
        for key, value in attrs.items():
            if value not in (None, ''):
                node.set(key, str(value))
        return node

    root = Element('REGZEC', {'xmlns': ns, 'version': DATA_VERSION})
    el(root, 'VENDOR', productName='Panther Security IS', productVersion='1.0')
    el(root, 'SENDER', VerzeProtokolu='2.0')
    employees = SubElement(root, 'employees')

    start = employee.start_employment_date
    employee_node = el(employees, 'employee', sqnr=1, dep=company['dep'], act=1, dat=today.isoformat())

    # Osoba
    client = el(employee_node, 'client', bno=_digits(employee.birth_number))
    el(client, 'name', sur=_clean(employee.last_name), fir=_clean(employee.first_name))
    el(client, 'birth', dat=employee.birth_date.isoformat(), nam=_clean(employee.birth_surname),
       cit=_clean(employee.birth_place), stat=(employee.birth_country or 'CZ').upper())
    el(client, 'stat', mal=employee.sex_from_birth_number, cnt=(employee.citizenship or 'CZ').upper())
    house = _digits(employee.house_number) or _digits(employee.orientation_number)
    orientation = _clean(employee.orientation_number) if _digits(employee.house_number) else ''
    el(client, 'adr', str=_clean(employee.street) or None, num=house, onum=orientation or None,
       pnu=_digits(employee.zip_code), cit=_clean(employee.city), cnt='CZ')
    el(client, 'taxidrezid', stat='CZ')

    # Zaměstnavatel
    el(employee_node, 'comp', vs=company['vs'], nam=company['name'])

    # Zaměstnání
    concluded = employee.contract_generated_at
    if concluded is not None:
        concluded = timezone.localtime(concluded).date() if timezone.is_aware(concluded) else concluded.date()
    contract_from = min(concluded, start) if concluded else start
    fixed_term, open_ended = POSITION_CODES[employee.contract_type]
    municipality = _clean(employee.work_municipality) or company['municipality']
    workplace = _clean(employee.work_location) or municipality
    position = getattr(employee, 'position', None)

    job = el(employee_node, 'job',
             fro=start.isoformat(),
             rel=ACTIVITY_CODES[employee.contract_type],
             relDetail=1,
             sme='N',
             contractfro=contract_from.isoformat(),
             relat=fixed_term if employee.contract_end_date else open_ended,
             workmode=company['workmode'],
             cont=company['continuous'],
             contractplace=workplace,
             cit=municipality,
             municode=_digits(employee.work_municipality_code) or company['municipality_code'])
    el(job, 'prof', clas=company['profession'])
    el(job, 'position', name=_clean(position.title if position else 'Strážný'), lead='N')

    el(employee_node, 'pens', early='N', reducedAge='N')
    el(employee_node, 'insh', cnr=employee.health_insurance_code)
    if employee.education:
        el(employee_node, 'fact', highedu=employee.education)
    el(employee_node, 'forinreg', juris='N')

    xml_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding='utf-8')

    errors = validate_regzec_xml(xml_bytes, year)
    if errors:
        raise RegzecDataError(["XML neprošlo kontrolou schématu ČSSZ: " + e for e in errors])
    return xml_bytes, year


def validate_regzec_xml(xml_bytes, year):
    """Ověří XML proti oficiálnímu XSD. Vrací seznam chyb (prázdný = v pořádku)."""
    try:
        from lxml import etree
    except ImportError:
        return []  # bez lxml kontrolu přeskočíme, ČSSZ ji provede při příjmu

    schema = etree.XMLSchema(etree.parse(SCHEMAS[year]['xsd']))
    document = etree.fromstring(xml_bytes)
    if schema.validate(document):
        return []
    return [f"řádek {err.line}: {err.message}" for err in schema.error_log]

# ---------------------------------------------------------------------------
# Odhláška zaměstnance – REGZEC akce 2 (skončení zaměstnání)
# Zdroj: Všeobecné zásady pro vyplňování Registrace zaměstnance (od 1. 7. 2026)
# a vzory REGZEC_Akce2_*.xml z developers.mpsv.cz.
# ---------------------------------------------------------------------------

DEREGISTRATION_DAYS = 8         # odhlásit do 8 dnů ode dne skončení zaměstnání

# Číselník C_DUVUKPRACVZT – důvod ukončení pracovněprávního vztahu (pro úřad práce)
TERMINATION_REASONS = [
    ('1', 'Ukončení PP cizince či osoby bez státní příslušnosti (§ 48 odst. 3 ZP)'),
    ('2', 'Dohodou se zaměstnavatelem (§ 49 ZP)'),
    ('3', 'Výpověď ze strany zaměstnance (§ 50 odst. 3 ZP)'),
    ('4', 'Organizační důvod (§ 52 písm. a–c ZP)'),
    ('5', 'Zdravotní důvody (§ 52 písm. d, e, § 56 odst. 1 písm. a ZP)'),
    ('6', 'Nesplňuje předpoklady nebo požadavky pro výkon práce (§ 52 písm. f ZP)'),
    ('7', 'Porušení povinností zvlášť hrubým způsobem (§ 52 písm. g, § 55 odst. 1 písm. b ZP)'),
    ('8', 'Soustavné méně závažné porušování povinností (§ 52 písm. g ZP)'),
    ('9', 'Porušení režimu dočasně práce neschopného zvlášť hrubým způsobem (§ 52 písm. h ZP)'),
    ('10', 'Okamžité zrušení – pravomocné odsouzení za úmyslný trestný čin (§ 55 odst. 1 písm. a ZP)'),
    ('11', 'Porušení podstatné povinnosti zaměstnavatelem (§ 56 odst. 1 písm. b ZP)'),
    ('12', 'Uplynutí doby určité (§ 65 ZP)'),
    ('13', 'Ve zkušební době zaměstnavatelem (§ 66 ZP)'),
    ('14', 'Ve zkušební době zaměstnancem (§ 66 ZP)'),
    ('15', 'Ostatní'),
]
# U organizačních a zdravotních důvodů je povinný údaj, zda náleží odstupné
SEVERANCE_REQUIRED_REASONS = {'4', '5'}
# Druh odstupného – atribut v XML podle verze schématu (2027 přejmenovalo odstupné)
SEVERANCE_ATTRS = {
    2025: {'severance': 'goldenhandshake', 'replacement': 'replacement'},
    2027: {'severance': 'severencebenefit', 'replacement': 'replacement'},
}

_PROTOCOL_ITEM = re.compile(r'<Item\b[^>]*\bsqnr="1"[^>]*>')
_PROTOCOL_ANY_ITEM = re.compile(r'<Item\b[^>]*>')
_PROTOCOL_IDENTIFIER = re.compile(r'\bidentifier="(\d*);(\d*);(\d*)"')


def parse_protocol_identifiers(protocol_xml):
    """
    Z protokolu ČSSZ k podání REGZEC vytáhne identifikátory zaměstnance.
    Položka Item má atribut identifier ve tvaru „rodné_číslo;IK_MPSV;ID_PPV“.
    Vrací {'birth_number', 'ikmpsv', 'job_id'} (prázdné řetězce, když chybí).
    """
    empty = {'birth_number': '', 'ikmpsv': '', 'job_id': ''}
    item = _PROTOCOL_ITEM.search(protocol_xml or '')
    match = _PROTOCOL_IDENTIFIER.search(item.group(0)) if item else None
    if not match:
        return empty
    return {'birth_number': match.group(1), 'ikmpsv': match.group(2), 'job_id': match.group(3)}


def protocol_birth_number(protocol_xml):
    """Rodné číslo z položky formuláře v protokolu ČSSZ (identifier začíná rodným číslem), nebo ''."""
    item = _PROTOCOL_ITEM.search(protocol_xml or '')
    identifier = _attrs(item.group(0)).get('identifier', '') if item else ''
    return _digits(identifier.split(';')[0])


def parse_protocol_items(protocol_xml):
    """Všechny přijaté položky protokolu (podání cizím programem jich může mít víc): list {'birth_number', 'ikmpsv', 'job_id'}."""
    items = []
    for tag in _PROTOCOL_ANY_ITEM.findall(protocol_xml or ''):
        attrs = _attrs(tag)
        parts = (attrs.get('identifier', '').split(';') + ['', ''])[:3]
        if attrs.get('sqnr') and attrs.get('result', '').upper() == 'OK' and _digits(parts[0]):
            items.append({'birth_number': _digits(parts[0]), 'ikmpsv': _digits(parts[1]), 'job_id': _digits(parts[2])})
    return items


_PROCESSING_RESULT = re.compile(r'<ProcessingResult\b[^>]*>')
_ATTR = re.compile(r'\b(\w+)="([^"]*)"')


def _attrs(tag):
    from html import unescape
    return {key: unescape(value) for key, value in _ATTR.findall(tag or '')}


def parse_protocol_result(protocol_xml):
    """
    Výsledek zpracování podání podle protokolu ČSSZ (ProcessingResult):
    {'result': 'OK' | 'ERROR' | '', 'number': kód chyby, 'message': text chyby}.
    Podáváme vždy jen jednoho zaměstnance, takže o přijetí rozhoduje celkový result;
    text chyby bereme z položky formuláře (sqnr=1), jinak z celkového výsledku.
    """
    top = _PROCESSING_RESULT.search(protocol_xml or '')
    if not top:
        return {'result': '', 'number': '', 'message': ''}
    overall = _attrs(top.group(0))
    item = _PROTOCOL_ITEM.search(protocol_xml)
    item = _attrs(item.group(0)) if item else {}

    result = 'OK' if overall.get('result', '').upper() == 'OK' else 'ERROR'
    if result == 'OK':
        return {'result': 'OK', 'number': '', 'message': ''}
    message = item.get('errMsg') or overall.get('errMsg') or 'ČSSZ podání odmítla bez udání důvodu.'
    number = item.get('errNum') or overall.get('errNumber') or ''
    return {'result': 'ERROR', 'number': number, 'message': message}


def check_deregistration_data(employee, data, test=False, today=None):
    """
    Kontrola údajů pro odhlášku. `data` je slovník z formuláře odhlášky:
    ikmpsv, job_id, no_insurance, reason, avg_net, periods [(od, do)],
    severance_belongs ('A'/'N'/''), severance_type, severance_amount, severance_paid_full ('A'/'N'/'').
    Vrací seznam problémů česky (prázdný = lze podat).
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    company = employer_values(test)
    problems = []

    if len(company['vs']) != 10:
        problems.append("Odesíláte do testovací datovky – nastavte testovací VS od ČSSZ (CSSZ_TEST_VS), skutečný VS testovací ČSSZ nezná." if test
                        else "Variabilní symbol zaměstnavatele musí mít 10 číslic (COMPANY_CSSZ_VS).")
    if len(company['dep']) != 3:
        problems.append("Kód okresní správy sociálního zabezpečení musí mít 3 číslice (COMPANY_CSSZ_DEP).")
    if employee.contract_type not in ACTIVITY_CODES:
        problems.append(f"Typ smlouvy {employee.get_contract_type_display()} se na ČSSZ nehlásí jako zaměstnanec.")

    if len(_digits(data.get('ikmpsv'))) != 10:
        problems.append("OIČ (IK MPSV) musí mít 10 číslic – najdete ho v protokolu ČSSZ k přihlášce.")
    if not 1 <= len(_digits(data.get('job_id'))) <= 22:
        problems.append("Chybí ID zaměstnání (ID PPV) – najdete ho v protokolu ČSSZ k přihlášce.")

    end = employee.termination_date
    if not end:
        problems.append("Zaměstnanec nemá zadané datum skončení zaměstnání.")
    elif end > today:
        problems.append(f"Odhlášku lze podat až po skončení zaměstnání, tedy od {end:%d.%m.%Y}.")
    elif employee.start_employment_date and end < employee.start_employment_date:
        problems.append("Datum skončení je dřív než datum nástupu.")

    if data.get('no_insurance'):
        return problems  # jen důvod neposkytnutí podkladů 2, nic dalšího se nevyplňuje

    reason = str(data.get('reason') or '')
    if reason not in dict(TERMINATION_REASONS):
        problems.append("Vyberte důvod ukončení pracovněprávního vztahu.")
    avg_net = data.get('avg_net')
    if avg_net in (None, '') or int(avg_net) <= 0:
        problems.append("Zadejte průměrný měsíční čistý (pravděpodobný) výdělek v celých korunách.")

    periods = data.get('periods') or []
    if not periods:
        problems.append("Zadejte aspoň jedno období důchodového pojištění (za posledních 24 měsíců).")
    for start, stop in periods:
        if start > stop:
            problems.append(f"Období {start:%d.%m.%Y} – {stop:%d.%m.%Y} má začátek po konci.")
        elif end and stop > end:
            problems.append(f"Období {start:%d.%m.%Y} – {stop:%d.%m.%Y} končí až po skončení zaměstnání.")
        elif employee.start_employment_date and start < employee.start_employment_date:
            problems.append(f"Období od {start:%d.%m.%Y} začíná před nástupem do zaměstnání.")

    belongs = data.get('severance_belongs') or ''
    if reason in SEVERANCE_REQUIRED_REASONS and belongs not in ('A', 'N'):
        problems.append("U organizačních a zdravotních důvodů vyberte, zda náleží odstupné.")
    if belongs == 'A':
        if data.get('severance_paid_full') not in ('A', 'N'):
            problems.append("Vyberte, zda bylo odstupné vyplaceno v plné výši.")
        amount = data.get('severance_amount')
        if amount in (None, '') or int(amount) <= 0:
            problems.append("Zadejte částku odstupného (zúčtovanou k výplatě) v celých korunách.")
    return problems


def build_deregistration_xml(employee, data, test=False, today=None):
    """
    Sestaví odhlášku (REGZEC akce 2) a ověří ji proti XSD.
    Vrací (xml_bytes, rok_schematu). Při chybějících údajích vyhodí RegzecDataError.
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    problems = check_deregistration_data(employee, data, test=test, today=today)
    if problems:
        raise RegzecDataError(problems)

    company = employer_values(test)
    year = schema_year_for(employee.termination_date)
    ns = SCHEMAS[year]['ns']

    def el(parent, tag, **attrs):
        node = SubElement(parent, tag)
        for key, value in attrs.items():
            if value not in (None, ''):
                node.set(key, str(value))
        return node

    root = Element('REGZEC', {'xmlns': ns, 'version': DATA_VERSION})
    el(root, 'VENDOR', productName='Panther Security IS', productVersion='1.0')
    el(root, 'SENDER', VerzeProtokolu='2.0')
    employees = SubElement(root, 'employees')
    employee_node = el(employees, 'employee', sqnr=1, dep=company['dep'], act=2, dat=today.isoformat())

    el(employee_node, 'client', ikmpsv=_digits(data['ikmpsv']))
    el(employee_node, 'comp', vs=company['vs'], nam=company['name'])
    el(employee_node, 'job',
       oid=_digits(data['job_id']),
       rel=ACTIVITY_CODES[employee.contract_type],
       relDetail=1,
       to=employee.termination_date.isoformat(),
       endbydeath='N')

    if data.get('no_insurance'):
        # Zaměstnání nezaložilo účast na pojištění (např. DPP pod limitem) – jen důvod 2
        el(employee_node, 'unemplcomp', rsn=2)
    else:
        attrs = {
            'typeempl': 1,  # pracovněprávní vztah (ne služební poměr)
            'avgmonear': int(data['avg_net']),
            'rsnterempl': data['reason'],
        }
        if data.get('severance_belongs') in ('A', 'N'):
            attrs['belong'] = data['severance_belongs']
        if data.get('severance_belongs') == 'A':
            attrs['fullpay'] = data['severance_paid_full']
            attr_name = SEVERANCE_ATTRS[year][data.get('severance_type') or 'severance']
            attrs[attr_name] = int(data['severance_amount'])
        unemployment = el(employee_node, 'unemplcomp', **attrs)
        for start, stop in data['periods']:
            el(unemployment, 'pensionperiod', fro=start.isoformat(), to=stop.isoformat())

    xml_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding='utf-8')

    errors = validate_regzec_xml(xml_bytes, year)
    if errors:
        raise RegzecDataError(["XML neprošlo kontrolou schématu ČSSZ: " + e for e in errors])
    return xml_bytes, year
