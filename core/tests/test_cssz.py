"""ČSSZ: odhláška (REGZEC akce 2), protokoly a jejich vyhodnocení."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core.models import CsszSubmission, Employee, SystemRole
from core.services import cssz_submit
from core.services.cssz import (
    build_deregistration_xml,
    check_deregistration_data,
    check_regzec_data,
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
