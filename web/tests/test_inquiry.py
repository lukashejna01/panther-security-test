"""Poptávkový formulář na webu: past na roboty, limit, kontrola vstupů."""

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from web.models import ServiceInquiry

HTTPS = {'HTTP_HOST': 'www.panther-security.cz', 'secure': True}
BASE = {'contact_name': 'Petr', 'phone': '777123456', 'service_type': 'PHYSICAL'}


class InquiryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse('web:submit_inquiry')

    def send(self, ip='3.3.3.3', **extra):
        return Client().post(self.url, {**BASE, **extra}, HTTP_X_REAL_IP=ip, **HTTPS)

    def test_valid_inquiry_is_saved(self):
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(ServiceInquiry.objects.count(), 1)

    def test_honeypot_pretends_success(self):
        self.assertEqual(self.send(website='http://spam').status_code, 200)
        self.assertEqual(ServiceInquiry.objects.count(), 0)

    def test_invalid_inputs(self):
        self.assertEqual(self.send(service_type='X').status_code, 400)
        self.assertEqual(self.send(contact_name='a' * 200).status_code, 400)
        self.assertEqual(self.send(email='neni-email').status_code, 400)

    def test_rate_limit(self):
        for _ in range(5):
            self.send(ip='6.6.6.6')
        self.assertEqual(self.send(ip='6.6.6.6').status_code, 429)
