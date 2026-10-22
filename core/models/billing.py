"""
Fakturační a dodavatelské agendy Panther Security:
Vydané faktury klientům, přijaté faktury od dodavatelů a položky faktur.
"""

from decimal import Decimal
from django.db import models
from django.utils import timezone


class Supplier(models.Model):
    """Externí dodavatel služeb nebo materiálu."""
    name = models.CharField(max_length=200, verbose_name="Název dodavatele")
    ico = models.CharField(max_length=20, blank=True, verbose_name="IČO")
    dic = models.CharField(max_length=20, blank=True, verbose_name="DIČ")
    street = models.CharField(max_length=150, blank=True, verbose_name="Ulice a č.p.")
    city = models.CharField(max_length=100, blank=True, verbose_name="Město")
    zip_code = models.CharField(max_length=20, blank=True, verbose_name="PSČ")
    bank_account = models.CharField(max_length=50, blank=True, verbose_name="Číslo účtu")
    contact_person = models.CharField(max_length=150, blank=True, verbose_name="Kontaktní osoba")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Telefon")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    notes = models.TextField(blank=True, verbose_name="Poznámka")

    class Meta:
        verbose_name = "Dodavatel"
        verbose_name_plural = "Dodavatelé"
        ordering = ['name']

    def __str__(self):
        return self.name


class InvoiceType(models.TextChoices):
    OUTGOING = 'OUTGOING', 'Vydaná faktura (Odběratel)'
    INCOMING = 'INCOMING', 'Přijatá faktura (Dodavatel)'


class InvoiceStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Neuhrazeno'
    PAID = 'PAID', 'Uhrazeno'
    OVERDUE = 'OVERDUE', 'Po splatnosti'
    CANCELLED = 'CANCELLED', 'Stornováno'


class Invoice(models.Model):
    """Daňový doklad / faktura."""
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.OUTGOING)
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="Číslo dokladu")
    variable_symbol = models.CharField(max_length=50, blank=True, verbose_name="Variabilní symbol")

    # Vztahy přes řetězec bez kruhového importu
    client = models.ForeignKey('core.Client', on_delete=models.CASCADE, null=True, blank=True, related_name="invoices", verbose_name="Klient (odběratel)")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices", verbose_name="Dodavatel")

    # Data vytěžená z přijaté faktury
    supplier_name = models.CharField(max_length=200, blank=True, verbose_name="Název dodavatele (z faktury)")
    supplier_ico = models.CharField(max_length=20, blank=True, verbose_name="IČO dodavatele")
    supplier_dic = models.CharField(max_length=20, blank=True, verbose_name="DIČ dodavatele")
    supplier_bank_account = models.CharField(max_length=50, blank=True, verbose_name="Bankovní účet dodavatele")

    # Finanční položky
    amount_without_vat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Částka bez DPH")
    vat_rate = models.PositiveIntegerField(default=21, verbose_name="Sazba DPH (%)")
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="DPH")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Celková částka s DPH")

    # Termíny
    issue_date = models.DateField(verbose_name="Datum vystavení")
    tax_date = models.DateField(verbose_name="DUZP (Datum uskutečnění zdanitelného plnění)")
    due_date = models.DateField(verbose_name="Datum splatnosti")
    paid_at = models.DateField(null=True, blank=True, verbose_name="Datum úhrady")

    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.UNPAID, verbose_name="Stav úhrady")
    notes = models.TextField(blank=True, verbose_name="Poznámka / Platební instrukce")
    document_file = models.FileField(upload_to="invoices/", null=True, blank=True, verbose_name="Naskenovaný originál faktury")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Faktura"
        verbose_name_plural = "Faktury"
        ordering = ['-issue_date']

    def __str__(self):
        return f"{self.get_invoice_type_display()} #{self.invoice_number} ({self.total_amount} Kč)"

    @property
    def is_paid(self):
        return self.status == InvoiceStatus.PAID

    @property
    def payment_badge(self):
        """Inteligentní výpočet stavu splatnosti a dnů po splatnosti."""
        if self.is_paid:
            return {
                'label': f"Uhrazeno ({self.paid_at.strftime('%d.%m.%Y') if self.paid_at else 'Zaplaceno'})",
                'css_class': 'green',
                'status_type': 'paid',
                'days': 0,
            }

        today = timezone.localdate()
        diff = (today - self.due_date).days

        if diff > 0:
            return {
                'label': f"Po splatnosti ({diff} {'den' if diff == 1 else 'dny' if diff < 5 else 'dní'})",
                'css_class': 'red',
                'status_type': 'overdue',
                'days': diff,
            }
        elif diff == 0:
            return {
                'label': "Dnes splatná!",
                'css_class': 'yellow',
                'status_type': 'today',
                'days': 0,
            }
        else:
            remaining = abs(diff)
            return {
                'label': f"Neuhrazeno (zbývá {remaining} {'den' if remaining == 1 else 'dny' if remaining < 5 else 'dní'})",
                'css_class': 'yellow',
                'status_type': 'pending',
                'days': remaining,
            }


class InvoiceItem(models.Model):
    """Jednotlivý řádek vystavené faktury."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255, verbose_name="Popis služby / položky")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name="Počet / Hodin")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Jednotková cena bez DPH")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Celkem bez DPH")

    def __str__(self):
        return f"{self.description} ({self.quantity} x {self.unit_price} Kč)"