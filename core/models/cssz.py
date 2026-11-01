"""
Evidence podání na ČSSZ odeslaných datovou schránkou a protokolů, které ČSSZ vrátila.
"""

from django.contrib.auth.models import User
from django.db import models

from .employee import Employee


class CsszSubmission(models.Model):
    """Jedno podání (např. REGZEC – přihláška zaměstnance) odeslané na ČSSZ přes ISDS."""

    ENVIRONMENT_CHOICES = [
        ('test', 'Testovací prostředí'),
        ('prod', 'Ostré prostředí'),
    ]
    STATUS_CHOICES = [
        ('SENT', 'Odesláno, čeká na odpověď ČSSZ'),
        ('ANSWERED', 'ČSSZ odpověděla protokolem'),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='cssz_submissions',
        verbose_name="Zaměstnanec"
    )
    KIND_REGISTRATION = 'REGZEC'
    KIND_DEREGISTRATION = 'REGZEC_A2'
    KIND_CHOICES = [
        (KIND_REGISTRATION, 'Přihláška (nástup)'),
        (KIND_DEREGISTRATION, 'Odhláška (skončení)'),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_REGISTRATION, verbose_name="Druh podání")
    environment = models.CharField(max_length=4, choices=ENVIRONMENT_CHOICES, verbose_name="Prostředí")
    recipient_box = models.CharField(max_length=10, verbose_name="Datová schránka ČSSZ")
    dm_id = models.CharField(max_length=20, verbose_name="ID odeslané datové zprávy")
    filename = models.CharField(max_length=120, verbose_name="Název souboru")
    xml_content = models.TextField(verbose_name="Odeslané XML")
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name="Odesláno")
    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cssz_submissions',
        verbose_name="Odeslal"
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SENT', verbose_name="Stav")
    protocol_dm_id = models.CharField(max_length=20, blank=True, verbose_name="ID zprávy s protokolem")
    protocol_received_at = models.DateTimeField(null=True, blank=True, verbose_name="Protokol přijat")
    protocol_annotation = models.CharField(max_length=255, blank=True, verbose_name="Věc zprávy s protokolem")
    protocol_html = models.TextField(blank=True, verbose_name="Protokol (HTML)")
    protocol_xml = models.TextField(blank=True, verbose_name="Protokol (XML)")

    class Meta:
        verbose_name = "Podání na ČSSZ"
        verbose_name_plural = "Podání na ČSSZ"
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.kind} {self.employee.full_name} ({self.get_environment_display()}, {self.dm_id})"