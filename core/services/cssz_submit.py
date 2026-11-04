"""
Odeslání podání REGZEC (přihláška i odhláška) na ČSSZ datovou schránkou a dohledání protokolu, který ČSSZ vrátí.

Protokol přichází jako nová datová zpráva od ČSSZ (ze stejné schránky, kam jsme podání poslali)
s přílohami XML a HTML. K podání ho přiřadíme podle rodného čísla v protokolu (a ID naší zprávy,
pokud ho obsahuje), aby se výsledek nikdy nezapsal k jinému zaměstnanci. Přijatá ostrá odhláška
přesune zaměstnance do archivu.
"""

from datetime import datetime, timedelta

from .cssz import (
    _digits,
    build_deregistration_xml,
    build_regzec_xml,
    parse_protocol_identifiers,
    parse_protocol_items,
    parse_protocol_result,
    protocol_birth_number,
)
from .isds import IsdsError, client_from_settings


# Běžná doba uložení zprávy v datové schránce
IMPORT_DAYS = 90


def _settings():
    from django.conf import settings
    return settings


def isds_environment():
    return getattr(_settings(), 'ISDS_ENVIRONMENT', 'test')


def isds_configured():
    s = _settings()
    return bool(getattr(s, 'ISDS_USERNAME', '') and getattr(s, 'ISDS_PASSWORD', ''))


def cssz_databox(environment):
    s = _settings()
    return getattr(s, 'CSSZ_DATABOX_PROD', '5ffu6xk') if environment == 'prod' else getattr(s, 'CSSZ_DATABOX_TEST', '9tsaf6s')


def submit_regzec(employee, user=None):
    """
    Vygeneruje přihlášku zaměstnance (REGZEC), odešle ji na ČSSZ a uloží záznam o podání.
    V ostrém prostředí zároveň označí zaměstnance jako nahlášeného.
    Vyhazuje RegzecDataError (chybějící údaje) nebo IsdsError (datová schránka).
    """
    from django.utils import timezone
    from core.models import CsszSubmission

    environment = isds_environment()
    # Testovací ČSSZ zná jen fiktivní VS (CSSZ_TEST_VS) – skutečný by zamítla (chyba 103901619)
    xml_bytes, year = build_regzec_xml(employee, test=environment == 'test')

    recipient = cssz_databox(environment)
    filename = f"REGZEC{year % 100}_{employee.personal_number or employee.id}.xml"
    annotation = f"Registrace zaměstnance – {employee.last_name} {employee.first_name}"

    client = client_from_settings()
    dm_id = client.send_message(
        recipient_id=recipient,
        annotation=annotation,
        filename=filename,
        content=xml_bytes,
        sender_ref=employee.personal_number or '',
    )

    submission = CsszSubmission.objects.create(
        employee=employee,
        kind='REGZEC',
        environment=environment,
        recipient_box=recipient,
        dm_id=dm_id,
        filename=filename,
        xml_content=xml_bytes.decode('utf-8'),
        sent_by=user if getattr(user, 'is_authenticated', False) else None,
    )

    if environment == 'prod':
        employee.is_reported_cssz = True
        employee.reported_cssz_date = timezone.now()
        employee.save(update_fields=['is_reported_cssz', 'reported_cssz_date'])
    return submission


def submit_deregistration(employee, data, user=None):
    """
    Odešle odhlášku zaměstnance (REGZEC akce 2) na ČSSZ a uloží záznam o podání.
    V ostrém prostředí označí zaměstnance jako odhlášeného. `data` viz check_deregistration_data.
    Vyhazuje RegzecDataError (chybějící údaje) nebo IsdsError (datová schránka).
    """
    from django.utils import timezone
    from core.models import CsszSubmission

    environment = isds_environment()
    xml_bytes, year = build_deregistration_xml(employee, data, test=environment == 'test')

    recipient = cssz_databox(environment)
    filename = f"REGZEC{year % 100}_odhlaska_{employee.personal_number or employee.id}.xml"
    annotation = f"Odhláška zaměstnance – {employee.last_name} {employee.first_name}"

    client = client_from_settings()
    dm_id = client.send_message(
        recipient_id=recipient,
        annotation=annotation,
        filename=filename,
        content=xml_bytes,
        sender_ref=employee.personal_number or '',
    )

    submission = CsszSubmission.objects.create(
        employee=employee,
        kind=CsszSubmission.KIND_DEREGISTRATION,
        environment=environment,
        recipient_box=recipient,
        dm_id=dm_id,
        filename=filename,
        xml_content=xml_bytes.decode('utf-8'),
        sent_by=user if getattr(user, 'is_authenticated', False) else None,
    )

    if environment == 'prod':
        employee.is_deregistered_cssz = True
        employee.deregistered_cssz_date = timezone.now()
        employee.save(update_fields=['is_deregistered_cssz', 'deregistered_cssz_date'])
    return submission


def apply_protocol_result(submission):
    """
    Zapíše k podání výsledek z protokolu ČSSZ. Když ČSSZ ostré podání odmítla,
    vrátí zaměstnance mezi nenahlášené (přihláška) / neodhlášené (odhláška),
    aby lhůta v aplikaci znovu svítila – pokud mezitím neodešlo novější podání.
    """
    outcome = parse_protocol_result(submission.protocol_xml)
    submission.protocol_result = outcome['result']
    submission.protocol_error = (f"[{outcome['number']}] " if outcome['number'] else '') + outcome['message']
    submission.save(update_fields=['protocol_result', 'protocol_error'])

    if outcome['result'] == 'OK':
        remember_identifiers(submission)
        archive_after_deregistration(submission)
        return
    if outcome['result'] != 'ERROR' or submission.environment != 'prod':
        return

    newer = submission.employee.cssz_submissions.filter(
        kind=submission.kind, environment='prod', sent_at__gt=submission.sent_at
    ).exists()
    if newer:
        return
    employee = submission.employee
    if submission.kind == submission.KIND_REGISTRATION:
        employee.is_reported_cssz = False
        employee.reported_cssz_date = None
        employee.save(update_fields=['is_reported_cssz', 'reported_cssz_date'])
    elif submission.kind == submission.KIND_DEREGISTRATION:
        employee.is_deregistered_cssz = False
        employee.deregistered_cssz_date = None
        employee.save(update_fields=['is_deregistered_cssz', 'deregistered_cssz_date'])


def remember_identifiers(submission):
    """
    Z protokolu k ostré přihlášce uloží zaměstnanci OIČ a ID zaměstnání –
    jsou potřeba pro odhlášku. Už vyplněné hodnoty nepřepisuje.
    """
    if submission.kind != submission.KIND_REGISTRATION or submission.environment != 'prod':
        return
    ids = parse_protocol_identifiers(submission.protocol_xml)
    employee = submission.employee
    changed = []
    if ids['ikmpsv'] and not employee.cssz_ikmpsv:
        employee.cssz_ikmpsv = ids['ikmpsv']
        changed.append('cssz_ikmpsv')
    if ids['job_id'] and not employee.cssz_job_id:
        employee.cssz_job_id = ids['job_id']
        changed.append('cssz_job_id')
    if changed:
        employee.save(update_fields=changed)


def archive_after_deregistration(submission):
    """
    Přijatá ostrá odhláška přesune zaměstnance do archivu. Pojistka: rodné číslo (a ID zaměstnání,
    pokud je v protokolu) musí sedět – jinak zaměstnanec zůstane aktivní a archivuje se ručně z karty.
    """
    employee = submission.employee
    if submission.kind != submission.KIND_DEREGISTRATION or submission.environment != 'prod':
        return False
    if employee.is_archived or not employee.termination_date:
        return False
    ids = parse_protocol_identifiers(submission.protocol_xml)
    if protocol_birth_number(submission.protocol_xml) != _digits(employee.birth_number):
        return False
    if ids['job_id'] and employee.cssz_job_id and ids['job_id'] != _digits(employee.cssz_job_id):
        return False
    employee.move_to_archive()
    return True


def import_registration_identifiers():
    """
    Pro zaměstnance přihlášené na ČSSZ, kterým chybí OIČ nebo ID zaměstnání, je dohledá v protokolech
    v ostré datové schránce (podle rodného čísla). Když má člověk v protokolech víc různých ID zaměstnání,
    ID se nedoplní – nepoznali bychom, které je aktuální.
    Vrací {'filled': [...], 'ambiguous': [...], 'missing': [...]} – seznamy zaměstnanců.
    """
    from django.db.models import Q
    from django.utils import timezone
    from core.models import Employee

    environment = isds_environment()
    if environment != 'prod':
        raise IsdsError("Údaje z datovky lze načíst jen z ostré schránky (ISDS_ENVIRONMENT=prod).")

    employees = list(Employee.objects.filter(is_reported_cssz=True, is_archived=False)
                     .filter(Q(cssz_ikmpsv='') | Q(cssz_job_id='')))
    report = {'filled': [], 'ambiguous': [], 'missing': []}
    if not employees:
        return report

    client = client_from_settings()
    box = cssz_databox(environment)
    since = timezone.localtime().replace(tzinfo=None) - timedelta(days=IMPORT_DAYS)
    found = {}
    for record in client.list_received(since):
        if record['sender_id'] != box:
            continue
        for f in client.download_message(record['dm_id']):
            if f['name'].lower().endswith('.xml') or 'xml' in f['mime'].lower():
                for item in parse_protocol_items(f['content'].decode('utf-8', errors='replace')):
                    found.setdefault(item['birth_number'], []).append(item)

    for employee in employees:
        items = found.get(_digits(employee.birth_number), [])
        persons = {i['ikmpsv'] for i in items if i['ikmpsv']}
        jobs = {i['job_id'] for i in items if i['job_id']}
        changed = []
        if len(persons) == 1 and not employee.cssz_ikmpsv:
            employee.cssz_ikmpsv = persons.pop()
            changed.append('cssz_ikmpsv')
        if len(jobs) == 1 and not employee.cssz_job_id:
            employee.cssz_job_id = jobs.pop()
            changed.append('cssz_job_id')
        if changed:
            employee.save(update_fields=changed)
        if len(jobs) > 1 and not employee.cssz_job_id:
            report['ambiguous'].append(employee)
        elif employee.cssz_ikmpsv and employee.cssz_job_id:
            report['filled'].append(employee)
        else:
            report['missing'].append(employee)
    return report


def _parse_isds_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def check_protocols(employee=None):
    """
    Projde přijaté zprávy od ČSSZ a přiřadí protokoly k podáním, která na odpověď čekají.
    Vrací počet nově přiřazených protokolů.
    """
    from django.utils import timezone
    from core.models import CsszSubmission

    environment = isds_environment()
    pending = CsszSubmission.objects.filter(status='SENT', environment=environment).select_related('employee').order_by('sent_at')
    if employee is not None:
        pending = pending.filter(employee=employee)
    pending = list(pending)
    if not pending:
        return 0

    used_ids = set(CsszSubmission.objects.exclude(protocol_dm_id='').values_list('protocol_dm_id', flat=True))
    boxes = {s.recipient_box for s in pending}
    since = timezone.localtime(pending[0].sent_at).replace(tzinfo=None) - timedelta(minutes=2)

    client = client_from_settings()
    records = [r for r in client.list_received(since) if r['sender_id'] in boxes and r['dm_id'] not in used_ids]
    records.sort(key=lambda r: r['delivery_time'])

    assigned = 0
    for record in records:
        if not pending:
            break
        files = client.download_message(record['dm_id'])
        texts = []
        html, xml = '', ''
        for f in files:
            text = f['content'].decode('utf-8', errors='replace')
            texts.append(text)
            name, mime = f['name'].lower(), f['mime'].lower()
            if not html and (name.endswith(('.htm', '.html')) or 'html' in mime):
                html = text
            elif not xml and (name.endswith('.xml') or 'xml' in mime):
                xml = text
        haystack = ' '.join(texts) + ' ' + record['annotation'] + ' ' + record['recipient_ref']

        # Jiná zpráva od ČSSZ než protokol k podání
        if not parse_protocol_result(xml)['result']:
            continue

        delivered = _parse_isds_time(record['delivery_time'])
        candidates = [s for s in pending if s.recipient_box == record['sender_id']
                      and (delivered is None or s.sent_at <= delivered)]
        birth_number = protocol_birth_number(xml)
        if birth_number:
            candidates = [s for s in candidates if _digits(s.employee.birth_number) == birth_number]
        match = next((s for s in candidates if s.dm_id in haystack), None)
        if match is None and (birth_number or len(candidates) == 1):
            match = candidates[0] if candidates else None
        if match is None:
            continue

        match.status = 'ANSWERED'
        match.protocol_dm_id = record['dm_id']
        match.protocol_received_at = delivered or timezone.now()
        match.protocol_annotation = record['annotation'][:255]
        match.protocol_html = html
        match.protocol_xml = xml
        match.save()
        apply_protocol_result(match)
        pending.remove(match)
        assigned += 1
    return assigned


__all__ = [
    'IsdsError', 'check_protocols', 'cssz_databox', 'isds_configured', 'isds_environment',
    'apply_protocol_result', 'archive_after_deregistration', 'import_registration_identifiers',
    'remember_identifiers', 'submit_deregistration', 'submit_regzec',
]