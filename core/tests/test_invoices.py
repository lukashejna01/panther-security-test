"""Faktury: IBAN a QR platba, číslování, úprava, přepnutí úhrady."""

from datetime import date

from django.test import SimpleTestCase, TestCase, override_settings

from core.models import Client as Customer
from core.models import Invoice, InvoiceItem, InvoiceType, SystemRole
from core.views.billing_views import _format_iban

from .helpers import HTTPS, logged_in_client, make_employee


class IbanTests(SimpleTestCase):
    def test_valid_and_invalid_accounts(self):
        self.assertEqual(_format_iban('352412682', '0300'), 'CZ7803000000000352412682')
        self.assertEqual(_format_iban('19-2000145399', '0800'), 'CZ6508000000192000145399')
        self.assertEqual(_format_iban('CZ 7803 0000 0000 0352 4126 82', ''), 'CZ7803000000000352412682')
        for account, code in (('', ''), ('', '0300'), ('35241268x', '0300'), ('CZ7803000000000352412683', '')):
            self.assertIsNone(_format_iban(account, code))


class InvoiceTests(TestCase):
    def setUp(self):
        self.client = logged_in_client(make_employee('majitel', SystemRole.OWNER))
        self.customer = Customer.objects.create(name='Klient A', is_active=True)

    def post_invoice(self, **extra):
        data = {'client': self.customer.id, 'issue_date': '2026-11-01', 'tax_date': '2026-11-01', 'due_date': '2026-11-15',
                'item_description[]': ['Ostraha'], 'item_quantity[]': ['100'], 'item_price[]': ['250'], **extra}
        return self.client.post('/fakturace/vydat/nova/', data, **HTTPS)

    def test_numbering_skips_deleted_numbers(self):
        for _ in range(3):
            self.post_invoice()
        Invoice.objects.get(invoice_number='20260001').delete()
        self.post_invoice()
        self.assertTrue(Invoice.objects.filter(invoice_number='20260004').exists())

    def test_nonsense_price_does_not_crash(self):
        response = self.post_invoice(**{'item_price[]': ['abc']})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())

    @override_settings(COMPANY_BANK_ACCOUNT='', COMPANY_BANK_CODE='')
    def test_missing_bank_account_means_no_qr(self):
        self.post_invoice()
        html = self.client.get('/fakturace/20260001/', **HTTPS).content.decode()
        self.assertNotIn('data:image/svg+xml', html)
        self.assertIn('není nastavený', html)
        self.assertNotIn('123456789', html)

    @override_settings(COMPANY_BANK_ACCOUNT='352412682/0300', COMPANY_BANK_CODE='')
    def test_qr_and_iban(self):
        self.post_invoice()
        html = self.client.get('/fakturace/20260001/', **HTTPS).content.decode()
        self.assertIn('data:image/svg+xml', html)
        self.assertIn('CZ7803000000000352412682', html)
        self.assertNotIn('0300/0300', html)

    def test_edit_recalculates(self):
        self.post_invoice()
        invoice = Invoice.objects.get()
        self.client.post(f'/fakturace/{invoice.id}/upravit/', {
            'client': self.customer.id, 'issue_date': '2026-11-02', 'tax_date': '2026-11-02', 'due_date': '2026-11-16',
            'item_description[]': ['Ostraha', 'Výjezd'], 'item_quantity[]': ['100', '2'], 'item_price[]': ['250', '500,50'],
        }, **HTTPS)
        invoice.refresh_from_db()
        self.assertEqual((str(invoice.amount_without_vat), str(invoice.vat_amount), invoice.invoice_number),
                         ('26001.00', '5460.21', '20260001'))
        self.assertEqual(InvoiceItem.objects.filter(invoice=invoice).count(), 2)

    def test_toggle_paid_sets_date(self):
        self.post_invoice()
        invoice = Invoice.objects.get()
        self.client.post(f'/fakturace/{invoice.id}/zaplaceno/', {'next': 'https://evil.com/'}, **HTTPS)
        invoice.refresh_from_db()
        self.assertEqual((invoice.status, invoice.paid_at is not None), ('PAID', True))
        self.assertIsInstance(invoice.paid_at, date)
