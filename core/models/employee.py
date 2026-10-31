"""
Kmenová evidence zaměstnanců Panther Security a správa záloh.
Osobní údaje z OP, vazba na uživatelský účet, zdravotní pojišťovna,
údaje pro ČSSZ, samostatný archiv ukončených poměrů a zálohy na mzdu.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from .organization import Department, Position, SystemRole


def advance_pdf_path(instance, filename):
    """Cesta pro uložení generovaného PDF dokladu o záloze."""
    date_str = instance.created_at.strftime('%Y/%m') if instance.created_at else timezone.now().strftime('%Y/%m')
    return f"advances/{date_str}/VPD_{instance.id or 'new'}.pdf"


def bank_confirm_path(instance, filename):
    """Cesta pro uložení potvrzení o bankovním převodu."""
    date_str = instance.created_at.strftime('%Y/%m') if instance.created_at else timezone.now().strftime('%Y/%m')
    return f"advances/bank/{date_str}/{filename}"


class Employee(models.Model):
    """Kmenová karta zaměstnance (strážného nebo řídícího pracovníka)."""
    CONTRACT_CHOICES = [
        ('DPP', 'Dohoda o provedení práce (DPP)'),
        ('DPC', 'Dohoda o pracovní činnosti (DPČ)'),
        ('HPP', 'Hlavní pracovní poměr (HPP)'),
        ('OSVC', 'IČO / Živnost'),
    ]

    HEALTH_INSURANCE_CHOICES = [
        ('111', '111 - Všeobecná zdravotní pojišťovna (VZP)'),
        ('201', '201 - Vojenská zdravotní pojišťovna (VoZP)'),
        ('205', '205 - Česká průmyslová zdravotní pojišťovna (ČPZP)'),
        ('207', '207 - Oborová zdravotní pojišťovna (OZP)'),
        ('209', '209 - Zaměstnanecká pojišťovna Škoda (ZPŠ)'),
        ('211', '211 - Zdravotní pojišťovna ministerstva vnitra ČR (ZPMV ČR)'),
        ('213', '213 - Revírní bratrská pokladna (RBP)'),
    ]

    # Propojení s přihlašovacím účtem do systému
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='employee_profile',
        null=True,
        blank=True,
        verbose_name="Uživatelský účet"
    )

    # Vygenerované přístupové heslo pro rychlý přehled manažera
    generated_password = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="Vygenerované přístupové heslo"
    )

    personal_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Osobní číslo"
    )

    system_role = models.CharField(
        max_length=20,
        choices=SystemRole.choices,
        default=SystemRole.STAFF,
        verbose_name="Systémová role"
    )

    # Osobní a úřední údaje z OP
    first_name = models.CharField(max_length=50, verbose_name="Jméno")
    last_name = models.CharField(max_length=50, verbose_name="Příjmení")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Datum narození")
    birth_number = models.CharField(max_length=15, blank=True, verbose_name="Rodné číslo")
    id_card_number = models.CharField(max_length=50, blank=True, verbose_name="Číslo OP / pasu")

    # Kontakty
    phone = models.CharField(max_length=25, blank=True, verbose_name="Telefon")
    email = models.EmailField(blank=True, verbose_name="E-mail")

    # Adresa trvalého bydliště
    street = models.CharField(max_length=100, blank=True, verbose_name="Ulice")
    house_number = models.CharField(max_length=20, blank=True, verbose_name="Číslo popisné")
    orientation_number = models.CharField(max_length=20, blank=True, verbose_name="Číslo orientační")
    city = models.CharField(max_length=100, blank=True, verbose_name="Město / Obec")
    zip_code = models.CharField(max_length=10, blank=True, verbose_name="PSČ")

    # Zdravotní pojišťovna (kód 111, 201, atd.)
    health_insurance_code = models.CharField(
        max_length=10,
        choices=HEALTH_INSURANCE_CHOICES,
        default='111',
        verbose_name="Zdravotní pojišťovna"
    )

    # Pracovní zařazení & smlouva
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Oddělení"
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_employees",
        verbose_name="Hlavní pozice"
    )
    contract_type = models.CharField(
        max_length=10,
        choices=CONTRACT_CHOICES,
        default='DPP',
        verbose_name="Typ smlouvy"
    )
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=160.00,
        verbose_name="Základní hodinová mzda (Kč/h)"
    )

    # ČSSZ / OSSZ agenda (ONZ oznámení o nástupu)
    start_employment_date = models.DateField(
        default=timezone.now,
        verbose_name="Datum nástupu do zaměstnání"
    )
    is_reported_cssz = models.BooleanField(
        default=False,
        verbose_name="Nahlášeno na ČSSZ (ONZ)"
    )
    reported_cssz_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Datum odeslání na ČSSZ"
    )

    # Bankovní spojení pro výplaty
    bank_account = models.CharField(max_length=50, blank=True, verbose_name="Číslo bankovního účtu")

    # Archivace zaměstnance (Ukončený pracovní poměr)
    is_active = models.BooleanField(default=True, verbose_name="Aktivní zaměstnanec")
    is_archived = models.BooleanField(default=False, verbose_name="V archivu zaměstnanců")
    termination_date = models.DateField(null=True, blank=True, verbose_name="Datum ukončení poměru")
    termination_reason = models.CharField(max_length=255, blank=True, verbose_name="Důvod ukončení")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Vytvořen dne")

    class Meta:
        verbose_name = "Zaměstnanec"
        verbose_name_plural = "Zaměstnanci"
        ordering = ['last_name', 'first_name']

    def __str__(self):
        num_str = f" [{self.personal_number}]" if self.personal_number else ""
        return f"{self.last_name} {self.first_name}{num_str} ({self.get_system_role_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self):
        cp_co = ""
        if self.house_number and self.orientation_number:
            cp_co = f"{self.house_number}/{self.orientation_number}"
        elif self.house_number:
            cp_co = self.house_number
        elif self.orientation_number:
            cp_co = self.orientation_number

        street_part = f"{self.street} {cp_co}".strip() if self.street else cp_co
        city_part = f"{self.zip_code} {self.city}".strip()
        parts = [p for p in [street_part, city_part] if p]
        return ", ".join(parts) or "Adresa neuvedena"

    def save(self, *args, **kwargs):
        if not self.personal_number:
            prefix = "PS"
            existing_numbers = Employee.objects.filter(
                personal_number__startswith=prefix
            ).values_list('personal_number', flat=True)

            max_num = 0
            for num_str in existing_numbers:
                try:
                    num_val = int(num_str.replace(prefix, ""))
                    if num_val > max_num:
                        max_num = num_val
                except (ValueError, TypeError):
                    continue

            self.personal_number = f"{prefix}{max_num + 1:04d}"

        super().save(*args, **kwargs)


class AdvancePayment(models.Model):
    """Evidence záloh na mzdu (hotovostní i bankovní) s doklady."""
    METHOD_CHOICES = [
        ('CASH', 'Hotovost'),
        ('BANK', 'Převod na účet'),
    ]

    STATUS_CHOICES = [
        ('ISSUED', 'Vydáno / Uhrazeno'),
        ('SETTLED', 'Započteno do mzdy'),
        ('CANCELLED', 'Stornováno'),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='advances',
        verbose_name="Zaměstnanec"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Částka (Kč)"
    )
    payment_method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        default='CASH',
        verbose_name="Forma úhrady"
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='ISSUED',
        verbose_name="Stav zálohy"
    )

    # Hotovostní výdej: Digitální podpis z dotykového displeje a hotový PDF VPD doklad
    signature_data = models.TextField(
        blank=True,
        null=True,
        verbose_name="Digitální podpis (Base64)"
    )
    receipt_pdf = models.FileField(
        upload_to=advance_pdf_path,
        blank=True,
        null=True,
        verbose_name="Výdajový doklad (PDF)"
    )

    # Bankovní převod: Povinné potvrzení transakce z banky
    bank_confirmation = models.FileField(
        upload_to=bank_confirm_path,
        blank=True,
        null=True,
        verbose_name="Potvrzení z banky (PDF / snímek)"
    )

    # Metadata
    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_advances',
        verbose_name="Vydal manažer"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Datum a čas vydání"
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Poznámka / Účel"
    )

    class Meta:
        verbose_name = "Záloha"
        verbose_name_plural = "Zálohy"
        ordering = ['-created_at']

    def __str__(self):
        method_str = "Hotovost" if self.payment_method == 'CASH' else "Banka"
        return f"Záloha {self.amount} Kč – {self.employee.full_name} ({method_str}, {self.created_at.strftime('%d.%m.%Y %H:%M')})"