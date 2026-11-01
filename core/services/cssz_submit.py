"""
Odeslání podání REGZEC (přihláška i odhláška) na ČSSZ datovou schránkou a dohledání protokolu, který ČSSZ vrátí.

Protokol přichází jako nová datová zpráva od ČSSZ (ze stejné schránky, kam jsme podání poslali)
s přílohami XML a HTML. Přiřadíme ho k podání podle ID naší zprávy, pokud ho protokol obsahuje,
jinak k nejstaršímu podání téže schránky, které na odpověď ještě čeká.
"""

from datetime import datetime, timedelta

from .cssz import build_deregistration_xml, build_regzec_xml, parse_protocol_identifiers, parse_protocol_result
from .isds import IsdsError, client_from_settings


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
    # V testu použijeme fiktivní VS od ČSSZ, pokud je nastavený; jinak skutečný
    use_test_vs = environment == 'test' and bool(getattr(_settings(), 'CSSZ_TEST_VS', ''))
    xml_bytes, year = build_regzec_xml(employee, test=use_test_vs)

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
    use_test_vs = environment == 'test' and bool(getattr(_settings(), 'CSSZ_TEST_VS', ''))
    xml_bytes, year = build_deregistration_xml(employee, data, test=use_test_vs)

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
    pending = CsszSubmission.objects.filter(status='SENT', environment=environment).order_by('sent_at')
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

        delivered = _parse_isds_time(record['delivery_time'])
        match = next((s for s in pending if s.recipient_box == record['sender_id'] and s.dm_id in haystack), None)
        if match is None:
            match = next((s for s in pending if s.recipient_box == record['sender_id']
                          and (delivered is None or s.sent_at <= delivered)), None)
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
    'apply_protocol_result', 'remember_identifiers', 'submit_deregistration', 'submit_regzec',
]