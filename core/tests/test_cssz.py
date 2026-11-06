"""ČSSZ: odhláška (REGZEC akce 2), protokoly a jejich vyhodnocení."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core.forms.employee_forms import EmployeeEditForm
from core.models import CsszSubmission, Employee, SystemRole
from core.services import cssz_submit
from core.services.cssz_deregistration import deregistration_suggestions
from core.services.cssz_employee_list import EmployeeListError, apply_employee_list, parse_employee_list
from core.services.cssz import (
    build_deregistration_xml,
    check_deregistration_data,
    check_regzec_data,
    employer_values,
    parse_protocol_identifiers,
    parse_protocol_result,
)

from .helpers import HTTPS, logged_in_client, make_employee

COMPANY = dict(COMPANY_CSSZ_VS='8862067306', COMPANY_CSSZ_DEP='886', COMPANY_NAME='Panther Security s.r.o.')
OK = ('<ProcessingResult result="OK" errMsg="" errNumber="0"><Details><Item sqnr="" identifier="" result="OK"/>'
      '<Item sqnr="1" identifier="6805217573;1705000132;4002831003248" result="OK"/></Details></ProcessingResult>')
ERROR = ('<ProcessingResult result="ERROR" errMsg="x" errNumber="604"><Details><Item sqnr="" identifier="" result="OK"/>'
         '<Item errMsg="Období se překrývá." errNum="604" identifier="8560176130" result="ERROR" sqnr="1"/></Details></ProcessingResult>')


@override_settings(**COMPANY)
class DeregistrationXmlTests(SimpleTestCase):
    employee = SimpleNamespace(contract_type='HPP', termination_date=date(2026, 10, 31), start_employment_date=date(2024, 3, 1),
                               get_contract_type_display=lambda: 'HPP')
    data = dict(ikmpsv='4897834263', job_id='24234234', no_insurance=False, reason='4', avg_net=33569,
                periods=[(date(2024, 11, 1), date(2026, 10, 31))], severance_belongs='A', severance_type='severance',
                severance_amount=30000, severance_paid_full='A')

    def test_full_xml_passes_xsd(self):
        xml, year = build_deregistration_xml(self.employee, self.data, today=date(2026, 11, 2))
        self.assertEqual(year, 2025)
        for fragment in (b'act="2"', b'ikmpsv="4897834263"', b'oid="24234234"', b'goldenhandshake="30000"', b'<pensionperiod'):
            self.assertIn(fragment, xml)

    def test_without_insurance_only_reason_2(self):
        xml, _ = build_deregistration_xml(self.employee, dict(ikmpsv='4897834263', job_id='1', no_insurance=True), today=date(2026, 11, 2))
        self.assertIn(b'<unemplcomp rsn="2" />', xml)

    def test_2027_schema_renames_severance(self):
        employee = SimpleNamespace(**{**self.employee.__dict__, 'termination_date': date(2027, 1, 15)})
        data = {**self.data, 'periods': [(date(2025, 3, 1), date(2027, 1, 15))]}
        xml, year = build_deregistration_xml(employee, data, today=date(2027, 1, 18))
        self.assertEqual(year, 2027)
        self.assertIn(b'severencebenefit="30000"', xml)

    def test_checks(self):
        self.assertIn("až po skončení", ' '.join(check_deregistration_data(self.employee, self.data, today=date(2026, 10, 30))))
        problems = check_deregistration_data(self.employee, {**self.data, 'ikmpsv': '1', 'severance_amount': None}, today=date(2026, 11, 2))
        self.assertEqual(len(problems), 2)


class EmployerValuesTests(SimpleTestCase):
    @override_settings(**COMPANY, CSSZ_TEST_VS='1152039226', CSSZ_TEST_DEP='115')
    def test_test_environment_uses_test_employer(self):
        self.assertEqual((employer_values(test=True)['vs'], employer_values(test=True)['dep']), ('1152039226', '115'))
        self.assertEqual((employer_values()['vs'], employer_values()['dep']), ('8862067306', '886'))

    @override_settings(**COMPANY, CSSZ_TEST_VS='1152039226', CSSZ_TEST_DEP='')
    def test_test_dep_falls_back_to_company(self):
        self.assertEqual(employer_values(test=True)['dep'], '886')


class EmployerRegistrationCheckTests(TestCase):
    def _problems(self, since):
        employee = make_employee(f'novak{since}', start_employment_date=date(2026, 10, 1))
        with override_settings(**COMPANY, COMPANY_CSSZ_EMPLOYER_SINCE=since):
            return ' '.join(check_regzec_data(employee, today=date(2026, 9, 25)))

    def test_start_before_employer_registration_is_blocked(self):
        self.assertIn("až od 01.11.2026", self._problems('2026-11-01'))

    def test_start_after_registration_or_unset_passes(self):
        self.assertNotIn("registrovaná jako zaměstnavatel", self._problems('2026-10-01'))
        self.assertNotIn("registrovaná jako zaměstnavatel", self._problems(''))


class ProtocolParsingTests(SimpleTestCase):
    def test_identifiers_and_result(self):
        self.assertEqual(parse_protocol_identifiers(OK)['job_id'], '4002831003248')
        self.assertEqual(parse_protocol_result(OK)['result'], 'OK')
        self.assertEqual(parse_protocol_result(ERROR), {'result': 'ERROR', 'number': '604', 'message': 'Období se překrývá.'})
        self.assertEqual(parse_protocol_result('<html/>')['result'], '')


class ProtocolEffectTests(TestCase):
    def submission(self, xml, kind=CsszSubmission.KIND_REGISTRATION):
        employee = make_employee('jan', is_reported_cssz=True, is_deregistered_cssz=True)
        return CsszSubmission.objects.create(employee=employee, kind=kind, environment='prod', recipient_box='x', dm_id='1',
                                             filename='f', xml_content='x', status='ANSWERED', protocol_xml=xml)

    def test_accepted_registration_stores_identifiers(self):
        sub = self.submission(OK)
        cssz_submit.apply_protocol_result(sub)
        sub.employee.refresh_from_db()
        self.assertEqual((sub.employee.cssz_ikmpsv, sub.employee.cssz_job_id), ('1705000132', '4002831003248'))

    def test_rejected_registration_is_reopened(self):
        sub = self.submission(ERROR)
        cssz_submit.apply_protocol_result(sub)
        sub.employee.refresh_from_db()
        self.assertFalse(sub.employee.is_reported_cssz)
        self.assertIn('604', sub.protocol_error)


@override_settings(**COMPANY, ISDS_USERNAME='u', ISDS_PASSWORD='p', ISDS_ENVIRONMENT='prod')
class DeregistrationViewTests(TestCase):
    def test_send_once(self):
        client = logged_in_client(make_employee('manazer', SystemRole.MANAGER))
        end = timezone.localdate() - timedelta(days=2)
        employee = Employee.objects.create(first_name='Hana', last_name='Hlavní', contract_type='HPP', is_archived=True,
                                           start_employment_date=date(2025, 1, 6), termination_date=end, termination_type='AGREEMENT',
                                           is_reported_cssz=True, cssz_ikmpsv='1111111118', cssz_job_id='555')
        data = {'ikmpsv': '1111111118', 'job_id': '555', 'reason': '2', 'avg_net': '25000',
                'periods': f"06.01.2025 – {end:%d.%m.%Y}", 'severance_type': 'severance', 'send': '1'}
        fake = mock.Mock()
        fake.send_message.return_value = '999'
        with mock.patch.object(cssz_submit, 'client_from_settings', return_value=fake):
            client.post(f'/dispecink/zamestnanec/{employee.id}/cssz/odhlaska/', data, **HTTPS)
            client.post(f'/dispecink/zamestnanec/{employee.id}/cssz/odhlaska/', data, **HTTPS)
        employee.refresh_from_db()
        self.assertTrue(employee.is_deregistered_cssz)
        self.assertEqual(fake.send_message.call_count, 1)
        self.assertEqual(fake.send_message.call_args.kwargs['recipient_id'], '5ffu6xk')


PROTOCOL = '<ProcessingResult result="{r}" errMsg="" errNumber="0"><Details><Item sqnr="1" identifier="{i}" result="{r}"/></Details></ProcessingResult>'


def received(*protocols, sender='5ffu6xk'):
    """Falešná datová schránka: každý protokol je jedna přijatá zpráva."""
    fake = mock.Mock()
    fake.list_received.return_value = [
        {'dm_id': str(100 + n), 'sender_id': sender, 'annotation': '', 'recipient_ref': '',
         'delivery_time': (timezone.now() + timedelta(minutes=5)).isoformat()}
        for n in range(len(protocols))
    ]
    fake.download_message.side_effect = lambda dm_id: [
        {'name': 'protokol.xml', 'mime': 'text/xml', 'content': protocols[int(dm_id) - 100].encode()}
    ]
    return fake


@override_settings(**COMPANY, ISDS_USERNAME='u', ISDS_PASSWORD='p', ISDS_ENVIRONMENT='prod')
class ArchiveAfterDeregistrationTests(TestCase):
    def setUp(self):
        self.employee = make_employee('hana', birth_number='680521/7573', contract_type='HPP', is_reported_cssz=True,
                                      termination_date=date(2026, 10, 31), cssz_job_id='555', is_deregistered_cssz=True)
        self.submission = CsszSubmission.objects.create(
            employee=self.employee, kind=CsszSubmission.KIND_DEREGISTRATION, environment='prod',
            recipient_box='5ffu6xk', dm_id='1', filename='f', xml_content='x')

    def _check(self, *protocols):
        with mock.patch.object(cssz_submit, 'client_from_settings', return_value=received(*protocols)):
            found = cssz_submit.check_protocols()
        self.employee.refresh_from_db()
        self.employee.user.refresh_from_db()
        return found

    def test_accepted_deregistration_archives(self):
        self.assertEqual(self._check(PROTOCOL.format(r='OK', i='6805217573;1705000132;555')), 1)
        self.assertTrue(self.employee.is_archived)
        self.assertFalse(self.employee.is_active)
        self.assertFalse(self.employee.user.is_active)

    def test_rejected_deregistration_stays_active(self):
        self.assertEqual(self._check(PROTOCOL.format(r='ERROR', i='6805217573;;')), 1)
        self.assertFalse(self.employee.is_archived)
        self.assertFalse(self.employee.is_deregistered_cssz)

    def test_foreign_protocol_is_not_assigned(self):
        self.assertEqual(self._check(PROTOCOL.format(r='OK', i='0104161475;1;2')), 0)
        self.assertFalse(self.employee.is_archived)

    def test_other_message_from_cssz_is_ignored(self):
        self.assertEqual(self._check('<Oznameni/>'), 0)

    def test_other_job_id_does_not_archive(self):
        self.assertEqual(self._check(PROTOCOL.format(r='OK', i='6805217573;1705000132;999')), 1)
        self.assertFalse(self.employee.is_archived)

    @override_settings(ISDS_ENVIRONMENT='test')
    def test_test_environment_never_archives(self):
        CsszSubmission.objects.filter(id=self.submission.id).update(environment='test', recipient_box='9tsaf6s')
        with mock.patch.object(cssz_submit, 'client_from_settings',
                               return_value=received(PROTOCOL.format(r='OK', i='6805217573;1;555'), sender='9tsaf6s')):
            self.assertEqual(cssz_submit.check_protocols(), 1)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_archived)


@override_settings(**COMPANY, ISDS_USERNAME='u', ISDS_PASSWORD='p', ISDS_ENVIRONMENT='prod')
class ImportIdentifiersTests(TestCase):
    def _import(self, *protocols):
        with mock.patch.object(cssz_submit, 'client_from_settings', return_value=received(*protocols)):
            return cssz_submit.import_registration_identifiers()

    def test_fills_only_matching_employee(self):
        employee = make_employee('jan', birth_number='680521/7573', is_reported_cssz=True)
        other = make_employee('eva', birth_number='0104161475', is_reported_cssz=True)
        report = self._import(PROTOCOL.format(r='OK', i='6805217573;1705000132;555'))
        employee.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((employee.cssz_ikmpsv, employee.cssz_job_id), ('1705000132', '555'))
        self.assertEqual(other.cssz_job_id, '')
        self.assertEqual((report['filled'], report['missing']), ([employee], [other]))

    def test_two_jobs_are_not_guessed(self):
        employee = make_employee('jan', birth_number='6805217573', is_reported_cssz=True)
        report = self._import(PROTOCOL.format(r='OK', i='6805217573;1705000132;555'),
                              PROTOCOL.format(r='OK', i='6805217573;1705000132;777'))
        employee.refresh_from_db()
        self.assertEqual(employee.cssz_job_id, '')
        self.assertEqual(employee.cssz_ikmpsv, '1705000132')
        self.assertEqual(report['ambiguous'], [employee])

    def test_rejected_protocol_is_skipped(self):
        employee = make_employee('jan', birth_number='6805217573', is_reported_cssz=True)
        self.assertEqual(self._import(PROTOCOL.format(r='ERROR', i='6805217573;1;2'))['missing'], [employee])

    @override_settings(ISDS_ENVIRONMENT='test')
    def test_only_from_real_box(self):
        with self.assertRaises(cssz_submit.IsdsError):
            cssz_submit.import_registration_identifiers()


@override_settings(**COMPANY)
class TerminationFlowTests(TestCase):
    def setUp(self):
        self.client = logged_in_client(make_employee('manazer', SystemRole.MANAGER))

    def _terminate(self, employee):
        day = timezone.localdate().isoformat()
        return self.client.post(f'/dispecink/zamestnanec/{employee.id}/archivovat/',
                                {'termination_type': 'AGREEMENT', 'notice_date': day, 'termination_date': day}, **HTTPS)

    def test_reported_contract_stays_active_until_deregistered(self):
        employee = make_employee('jan', contract_type='HPP', is_reported_cssz=True)
        self._terminate(employee)
        employee.refresh_from_db()
        employee.user.refresh_from_db()
        self.assertIsNotNone(employee.termination_date)
        self.assertTrue(employee.is_active)
        self.assertFalse(employee.is_archived)
        self.assertTrue(employee.user.is_active)

    def test_manual_archive(self):
        employee = make_employee('jan', contract_type='HPP', termination_date=date(2026, 10, 31))
        self.client.post(f'/dispecink/zamestnanec/{employee.id}/archivovat-rucne/', **HTTPS)
        employee.refresh_from_db()
        self.assertTrue(employee.is_archived)

    def test_manual_archive_needs_termination(self):
        employee = make_employee('jan', contract_type='HPP')
        self.client.post(f'/dispecink/zamestnanec/{employee.id}/archivovat-rucne/', **HTTPS)
        employee.refresh_from_db()
        self.assertFalse(employee.is_archived)

    def test_before_app_mark(self):
        employee = make_employee('jan', contract_type='HPP')
        self.client.post(f'/dispecink/zamestnanec/{employee.id}/cssz/', {'action': 'before_app'}, **HTTPS)
        employee.refresh_from_db()
        self.assertTrue(employee.is_reported_cssz)
        self.assertEqual(employee.cssz_status['text'], "Přihlášen před aplikací")

    def test_pages_render_for_pending_employee(self):
        employee = make_employee('jan', contract_type='HPP', is_reported_cssz=True, termination_date=date(2026, 10, 31))
        detail = self.client.get(f'/dispecink/zamestnanec/{employee.id}/', **HTTPS)
        self.assertContains(detail, 'Archivovat bez protokolu')
        self.assertContains(detail, 'Načíst z datovky')
        self.assertContains(self.client.get('/dispecink/zamestnanci/', **HTTPS), 'čeká na odhlášku')


CSV_FILE = ("Rodné číslo;Příjmení a jméno;Variabilní symbol;Datum nástupu do zaměstnání;Datum skončení zaměstnání;Druh činnosti;ID zaměstnání;OIČ\n"
            "6805217573;Novák Jan;8862067306;1. 5. 2026;;T - první dohoda;4003155470643;1705000132\n"
            "0104161475;Hrubá Eva;8862067306;18. 8. 2025;;1 - první pracovní poměr;4003090941338;1461526858\n"
            "6403162029;Starý Petr;8862067306;1. 1. 2024;1. 2. 2025;1 - první pracovní poměr;111;1111111118\n").encode('utf-8')


class EmployeeListImportTests(TestCase):
    def test_parse_finished_job_is_skipped_and_cp1250_works(self):
        rows = parse_employee_list(CSV_FILE.decode('utf-8').encode('cp1250'))
        self.assertEqual([r['birth_number'] for r in rows], ['6805217573', '0104161475'])
        self.assertEqual((rows[0]['last_name'], rows[0]['first_name'], rows[0]['start'], rows[0]['contract_type']),
                         ('Novák', 'Jan', date(2026, 5, 1), 'DPP'))
        self.assertEqual(rows[1]['contract_type'], 'HPP')

    def test_real_eportal_export_format(self):
        content = ("Rodné číslo;Příjmení;Jméno;Variabilní symbol;Datum nástupu do zaměstnání;Datum skončení zaměstnání;"
                   "Druh činnosti - kód;Druh činnosti - název;Bližší určení zaměstnání - kód;Bližší určení zaměstnání - název;"
                   "ZMR;Identifikátor zaměstnání;OIČ\n"
                   "0104161475;Nováková;Eva;8862067306;01.05.2026;;T;první dohoda o provedení práce u téhož zaměstnavatele;"
                   "1;Žádné;N;4003155302851;1244387210\n").encode('utf-8')
        self.assertEqual(parse_employee_list(content), [{
            'birth_number': '0104161475', 'ikmpsv': '1244387210', 'job_id': '4003155302851', 'last_name': 'Nováková',
            'first_name': 'Eva', 'start': date(2026, 5, 1), 'contract_type': 'DPP',
        }])

    def test_unknown_columns_write_nothing(self):
        with self.assertRaises(EmployeeListError) as e:
            parse_employee_list(b'Jmeno;Telefon\nJan;123\n')
        self.assertIn('Telefon', str(e.exception))

    def test_fills_existing_and_reports_missing(self):
        employee = make_employee('jan', birth_number='680521/7573', contract_type='DPP', start_employment_date=date(2026, 5, 1))
        report = apply_employee_list(parse_employee_list(CSV_FILE))
        employee.refresh_from_db()
        self.assertEqual((employee.cssz_ikmpsv, employee.cssz_job_id), ('1705000132', '4003155470643'))
        self.assertTrue(employee.is_reported_cssz)
        self.assertTrue(employee.cssz_registered_before_app)
        self.assertEqual(report['missing'], ['Hrubá Eva'])
        self.assertEqual(report['mismatches'], [])
        self.assertEqual(Employee.objects.count(), 1)

    def test_create_missing_without_account(self):
        apply_employee_list(parse_employee_list(CSV_FILE), create_missing=True)
        eva = Employee.objects.get(last_name='Hrubá')
        self.assertIsNone(eva.user)
        self.assertEqual((eva.contract_type, eva.start_employment_date, eva.cssz_job_id), ('HPP', date(2025, 8, 18), '4003090941338'))
        self.assertEqual(eva.cssz_status['text'], "Přihlášen před aplikací")

    def test_does_not_overwrite_and_flags_mismatch(self):
        other = make_employee('jan', birth_number='6805217573', cssz_job_id='999')
        wrong = make_employee('eva', birth_number='0104161475', contract_type='DPP', start_employment_date=date(2026, 10, 1))
        report = apply_employee_list(parse_employee_list(CSV_FILE))
        other.refresh_from_db()
        self.assertEqual(other.cssz_job_id, '999')
        self.assertEqual(report['conflicts'], [other.full_name])
        wrong.refresh_from_db()
        self.assertEqual(wrong.start_employment_date, date(2026, 10, 1))
        self.assertEqual(len(report['mismatches']), 1)

    def test_upload_view(self):
        client = logged_in_client(make_employee('manazer', SystemRole.MANAGER))
        employee = make_employee('jan', birth_number='6805217573')
        upload = SimpleUploadedFile('seznam.csv', CSV_FILE, content_type='text/csv')
        response = client.post('/dispecink/zamestnanci/cssz/seznam-z-eportalu/', {'employee_list': upload}, **HTTPS)
        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertEqual(employee.cssz_ikmpsv, '1705000132')

    def test_before_app_employee_is_not_suggested_as_uninsured(self):
        employee = make_employee('jan', contract_type='HPP', start_employment_date=date(2025, 1, 1), termination_date=date(2026, 10, 31),
                                 cssz_registered_before_app=True)
        self.assertFalse(deregistration_suggestions(employee)['no_insurance'])


class EmployeeEditTests(TestCase):
    def _data(self, employee, **changes):
        form = EmployeeEditForm(instance=employee)
        data = {name: form[name].value() for name in form.fields}
        return {**{k: ('' if v is None else v) for k, v in data.items()}, **changes}

    def test_manager_edits_imported_employee_without_account(self):
        client = logged_in_client(make_employee('manazer', SystemRole.MANAGER))
        apply_employee_list(parse_employee_list(CSV_FILE), create_missing=True)
        employee = Employee.objects.get(last_name='Novák')
        url = f'/dispecink/zamestnanec/{employee.id}/upravit/'
        self.assertContains(client.get(url, **HTTPS), 'Upravit údaje zaměstnance')
        response = client.post(url, self._data(employee, phone='+420777123456', hourly_rate='200', last_name='Nováček'), **HTTPS)
        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertEqual((employee.phone, employee.hourly_rate, employee.last_name), ('+420777123456', 200, 'Nováček'))
        self.assertEqual(employee.cssz_job_id, '4003155470643')

    def test_name_is_synced_to_account_and_role_cannot_change(self):
        client = logged_in_client(make_employee('manazer', SystemRole.MANAGER))
        employee = make_employee('jan', start_employment_date=date(2026, 1, 5))
        client.post(f'/dispecink/zamestnanec/{employee.id}/upravit/',
                    self._data(employee, first_name='Honza', system_role=SystemRole.OWNER), **HTTPS)
        employee.refresh_from_db()
        employee.user.refresh_from_db()
        self.assertEqual(employee.user.first_name, 'Honza')
        self.assertEqual(employee.system_role, SystemRole.STAFF)

    def test_invalid_identifier_is_rejected(self):
        client = logged_in_client(make_employee('manazer', SystemRole.MANAGER))
        employee = make_employee('jan', start_employment_date=date(2026, 1, 5))
        response = client.post(f'/dispecink/zamestnanec/{employee.id}/upravit/', self._data(employee, cssz_ikmpsv='123'), **HTTPS)
        self.assertContains(response, 'OIČ má 10 číslic')
        employee.refresh_from_db()
        self.assertEqual(employee.cssz_ikmpsv, '')

    def test_staff_cannot_edit(self):
        employee = make_employee('jan', start_employment_date=date(2026, 1, 5))
        client = logged_in_client(make_employee('eva'))
        client.post(f'/dispecink/zamestnanec/{employee.id}/upravit/', self._data(employee, first_name='Hack'), **HTTPS)
        employee.refresh_from_db()
        self.assertEqual(employee.first_name, 'Jan')
