"""Bezpečnost: přihlášení, 2FA, hesla zaměstnanců, oprávnění, soubory, hlavičky."""

import time

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.models import Employee, Invoice, InvoiceType, SystemRole
from core.views.billing_views import _safe_return_url

from .helpers import HTTPS, logged_in_client, make_employee


class LoginLockoutTests(TestCase):
    def login(self, password, ip='1.1.1.1'):
        return Client().post('/prihlaseni/', {'username': 'jan', 'password': password}, HTTP_X_REAL_IP=ip, **HTTPS)

    def test_lockout_after_five_failures_only_for_same_ip(self):
        make_employee('jan')
        for _ in range(5):
            self.login('spatne')
        self.assertEqual(self.login('Silne-Heslo-2026').status_code, 429)
        self.assertEqual(self.login('Silne-Heslo-2026', ip='2.2.2.2').status_code, 302)


class TwoFactorTests(TestCase):
    def setUp(self):
        self.owner = make_employee('majitel', SystemRole.OWNER)
        self.client = logged_in_client(self.owner, verify_2fa=False)

    def code(self, device):
        totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
        totp.time = time.time()
        return f"{totp.token():06d}"

    def test_owner_without_2fa_is_sent_to_pairing(self):
        response = self.client.get('/fakturace/', **HTTPS)
        self.assertTrue(response['Location'].startswith('/overeni/sparovat/'))

    def test_pairing_gives_backup_codes_and_unlocks(self):
        self.client.get('/overeni/sparovat/', **HTTPS)
        device = TOTPDevice.objects.get(user=self.owner.user)
        response = self.client.post('/overeni/sparovat/', {'code': self.code(device), 'next': '/fakturace/'}, **HTTPS)
        self.assertContains(response, 'Aplikace je spárovaná')
        self.assertEqual(self.client.get('/fakturace/', **HTTPS).status_code, 200)

    def test_cannot_repair_with_password_only(self):
        TOTPDevice.objects.create(user=self.owner.user, name='t', confirmed=True)
        self.assertEqual(self.client.get('/overeni/sparovat/', **HTTPS)['Location'], '/overeni/')
        self.client.post('/overeni/znovu-sparovat/', **HTTPS)
        self.assertTrue(TOTPDevice.objects.filter(user=self.owner.user, confirmed=True).exists())

    def test_staff_and_manager_need_no_2fa(self):
        for username, role, url in (('strazny', SystemRole.STAFF, '/portal/'), ('manazer', SystemRole.MANAGER, '/dispecink/')):
            client = logged_in_client(make_employee(username, role))
            self.assertEqual(client.get(url, **HTTPS).status_code, 200)


class EmployeePasswordTests(TestCase):
    def test_reset_shows_password_once_and_forces_change(self):
        manager = make_employee('manazer', SystemRole.MANAGER)
        guard = make_employee('strazny')
        client = logged_in_client(manager)
        client.post(f'/dispecink/zamestnanec/{guard.id}/heslo/', **HTTPS)
        password = client.session['new_credentials']['password']
        self.assertContains(client.get(f'/dispecink/zamestnanec/{guard.id}/', **HTTPS), password)
        self.assertNotContains(client.get(f'/dispecink/zamestnanec/{guard.id}/', **HTTPS), password)

        guard_client = Client()
        guard_client.post('/prihlaseni/', {'username': 'strazny', 'password': password}, **HTTPS)
        self.assertEqual(guard_client.get('/portal/', **HTTPS)['Location'], '/profil/')

    def test_manager_cannot_reset_owner_or_manager(self):
        manager = make_employee('manazer', SystemRole.MANAGER)
        client = logged_in_client(manager)
        for target in (make_employee('majitel', SystemRole.OWNER), make_employee('manazer2', SystemRole.MANAGER)):
            before = User.objects.get(pk=target.user_id).password
            client.post(f'/dispecink/zamestnanec/{target.id}/heslo/', **HTTPS)
            self.assertEqual(User.objects.get(pk=target.user_id).password, before)


class AccessControlTests(TestCase):
    def test_staff_cannot_open_foreign_payslip_or_finance(self):
        guard = make_employee('strazny')
        other = make_employee('kolega')
        client = logged_in_client(guard)
        self.assertEqual(client.get(f'/portal/vyplatni-paska/{other.id}/2026/1/', **HTTPS)['Location'], '/portal/')
        self.assertNotEqual(client.get('/fakturace/', **HTTPS).status_code, 200)

    def test_state_changes_require_post(self):
        owner = make_employee('majitel', SystemRole.OWNER)
        client = logged_in_client(owner)
        invoice = Invoice.objects.create(invoice_type=InvoiceType.OUTGOING, invoice_number='20260001',
                                         issue_date='2026-01-01', tax_date='2026-01-01', due_date='2026-01-15')
        self.assertEqual(client.get(f'/fakturace/{invoice.id}/zaplaceno/', **HTTPS).status_code, 405)
        self.assertEqual(client.get('/smena/1/prevzit/', **HTTPS).status_code, 405)
        self.assertEqual(client.get('/smena/1/schvalit/', **HTTPS).status_code, 405)


class PrivateFilesTests(TestCase):
    def test_invoice_scan_only_for_owner_and_html_is_download(self):
        owner = make_employee('majitel', SystemRole.OWNER)
        invoice = Invoice.objects.create(invoice_type=InvoiceType.INCOMING, invoice_number='PF-1',
                                         issue_date='2026-01-01', tax_date='2026-01-01', due_date='2026-01-15',
                                         document_file=SimpleUploadedFile('zlo.html', b'<script>alert(1)</script>'))
        url = f'/fakturace/{invoice.id}/dokument/'
        self.assertTrue(Client().get(url, **HTTPS)['Location'].startswith('/prihlaseni/'))
        response = logged_in_client(owner).get(url, **HTTPS)
        self.assertTrue(response['Content-Disposition'].startswith('attachment'))


class HeadersAndRedirectTests(TestCase):
    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_https_redirect_and_security_headers(self):
        self.assertEqual(Client().get('/prihlaseni/', HTTP_HOST='www.panther-security.cz')['Location'],
                         'https://www.panther-security.cz/prihlaseni/')
        response = Client().get('/prihlaseni/', **HTTPS)
        self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])
        self.assertEqual(response['X-Frame-Options'], 'DENY')

    def test_open_redirect_is_blocked(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', HTTP_HOST='www.panther-security.cz', secure=True)
        self.assertEqual(_safe_return_url(request, '/fakturace/', 'X'), '/fakturace/')
        for evil in ('https://evil.com/', '//evil.com', 'javascript:alert(1)'):
            self.assertEqual(_safe_return_url(request, evil, 'X'), 'X')

    def test_robots_txt(self):
        response = Client().get('/robots.txt', **HTTPS)
        self.assertContains(response, 'Disallow: /')
        self.assertNotContains(response, 'admin')
