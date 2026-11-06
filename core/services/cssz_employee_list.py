"""
Import seznamu zaměstnanců z ePortálu ČSSZ (služba „Seznam zaměstnanců“, tlačítko Export CSV).

Podle rodného čísla doplní zaměstnancům v aplikaci OIČ a ID zaměstnání a označí je jako
přihlášené před aplikací. Datum nástupu ani typ smlouvy nepřepisuje, jen upozorní na neshodu.
Sloupce se hledají podle názvu; když chybí ty povinné, nic se nezapíše.
"""

import csv
import io
import re
import unicodedata
from datetime import date

from django.db import transaction

from .cssz import ACTIVITY_CODES, _digits

CONTRACT_BY_ACTIVITY = {code: contract for contract, code in ACTIVITY_CODES.items()}


class EmployeeListError(Exception):
    """Soubor nejde přečíst – text je určený pro uživatele."""


def _normalize(text):
    text = unicodedata.normalize('NFKD', text or '')
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).lower().split())


def _column_key(title):
    title = _normalize(title)
    words = set(re.findall(r'[a-z0-9]+', title))
    if 'rodne' in words and 'cislo' in words:
        return 'birth_number'
    if words & {'oic', 'ikmpsv'} or {'ik', 'mpsv'} <= words:
        return 'ikmpsv'
    if (words & {'id', 'identifikator'} and words & {'zamestnani', 'ppv'}) or 'idppv' in words:
        return 'job_id'
    if 'prijmeni' in words and 'jmeno' in words:
        return 'full_name'
    if 'prijmeni' in words and 'rodne' not in words:
        return 'last_name'
    if 'jmeno' in words:
        return 'first_name'
    if 'nastupu' in words or 'nastup' in words:
        return 'start'
    if 'skonceni' in words:
        return 'end'
    if 'druh' in words:
        return 'activity'
    return None


def _parse_date(value):
    numbers = re.findall(r'\d+', value or '')
    if len(numbers) < 3:
        return None
    try:
        if len(numbers[0]) == 4:
            return date(int(numbers[0]), int(numbers[1]), int(numbers[2]))
        return date(int(numbers[2]), int(numbers[1]), int(numbers[0]))
    except ValueError:
        return None


def parse_employee_list(content):
    """Z obsahu CSV vrátí řádky nekončících zaměstnání: list slovníků s údaji zaměstnance."""
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('cp1250', errors='replace')

    lines = [line for line in text.splitlines() if line.strip()]
    columns, first_row, seen = None, 0, []
    for index, line in enumerate(lines[:10]):
        delimiter = max(';,\t', key=line.count)
        titles = next(csv.reader([line], delimiter=delimiter))
        keys = {_column_key(title): position for position, title in reversed(list(enumerate(titles)))}
        # V hlášce smí být jen první řádek – další už můžou být osobní údaje
        seen = seen or titles
        if {'birth_number', 'ikmpsv', 'job_id'} <= keys.keys():
            columns, first_row = keys, index + 1
            break
    if columns is None:
        names = ', '.join(t.strip() for t in seen[:12] if not re.search(r'\d{4}', t)) or 'žádné'
        raise EmployeeListError("V souboru se nenašly sloupce rodné číslo, OIČ a ID zaměstnání. "
                                f"Nalezené sloupce: {names}. Nahrajte Export CSV ze Seznamu zaměstnanců.")

    rows = []
    for values in csv.reader(lines[first_row:], delimiter=delimiter):
        def cell(key):
            position = columns.get(key)
            return values[position].strip() if position is not None and position < len(values) else ''

        birth_number = _digits(cell('birth_number'))
        if not birth_number or _parse_date(cell('end')):
            continue
        activity = cell('activity').lstrip('=" ')[:1].upper()
        last_name, first_name = cell('last_name'), cell('first_name')
        if cell('full_name') and not last_name:
            last_name, _, first_name = cell('full_name').partition(' ')
        rows.append({
            'birth_number': birth_number,
            'ikmpsv': _digits(cell('ikmpsv')),
            'job_id': _digits(cell('job_id')),
            'last_name': last_name,
            'first_name': first_name,
            'start': _parse_date(cell('start')),
            'contract_type': CONTRACT_BY_ACTIVITY.get(activity),
        })
    if not rows:
        raise EmployeeListError("V souboru nejsou žádní zaměstnanci bez data skončení.")
    return rows


@transaction.atomic
def apply_employee_list(rows, create_missing=False):
    """Zapíše řádky ze seznamu. Vrací přehled: updated, created, missing, ambiguous, conflicts, mismatches."""
    from core.models import Employee

    report = {key: [] for key in ('updated', 'created', 'missing', 'ambiguous', 'conflicts', 'mismatches')}
    by_number = {}
    for employee in Employee.objects.filter(is_archived=False).exclude(birth_number=''):
        by_number.setdefault(_digits(employee.birth_number), []).append(employee)
    grouped = {}
    for row in rows:
        grouped.setdefault(row['birth_number'], []).append(row)

    for number, person_rows in grouped.items():
        row = person_rows[0]
        label = f"{row['last_name']} {row['first_name']}".strip() or f"RČ …{number[-4:]}"
        employees = by_number.get(number, [])
        if len(person_rows) > 1 or len(employees) > 1:
            report['ambiguous'].append(label)
            continue
        if not employees and not create_missing:
            report['missing'].append(label)
            continue
        if len(row['ikmpsv']) != 10 or not 1 <= len(row['job_id']) <= 22:
            report['ambiguous'].append(label)
            continue

        if not employees:
            Employee.objects.create(
                first_name=row['first_name'][:50], last_name=row['last_name'][:50], birth_number=number,
                start_employment_date=row['start'], contract_type=row['contract_type'] or Employee._meta.get_field('contract_type').default,
                is_reported_cssz=True, cssz_registered_before_app=True,
                cssz_ikmpsv=row['ikmpsv'], cssz_job_id=row['job_id'],
            )
            report['created'].append(label)
            continue

        employee = employees[0]
        if (employee.cssz_ikmpsv and _digits(employee.cssz_ikmpsv) != row['ikmpsv']) or \
                (employee.cssz_job_id and _digits(employee.cssz_job_id) != row['job_id']):
            report['conflicts'].append(employee.full_name)
            continue
        employee.cssz_ikmpsv, employee.cssz_job_id = row['ikmpsv'], row['job_id']
        changed = ['cssz_ikmpsv', 'cssz_job_id']
        if not employee.is_reported_cssz:
            employee.is_reported_cssz = True
            employee.reported_cssz_date = None
            employee.cssz_registered_before_app = True
            changed += ['is_reported_cssz', 'reported_cssz_date', 'cssz_registered_before_app']
        employee.save(update_fields=changed)
        report['updated'].append(employee.full_name)

        if (row['start'] and employee.start_employment_date != row['start']) or \
                (row['contract_type'] and employee.contract_type != row['contract_type']):
            report['mismatches'].append(
                f"{employee.full_name} (ČSSZ: nástup {row['start']:%d.%m.%Y}, {row['contract_type'] or '?'})"
                if row['start'] else employee.full_name
            )
    return report
