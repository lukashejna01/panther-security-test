"""
Kmenová evidence zaměstnanců Panther Security a správa záloh.
Osobní údaje z OP, vazba na uživatelský účet, zdravotní pojišťovna,
údaje pro ČSSZ, samostatný archiv ukončených poměrů a zálohy na mzdu.
"""

import secrets

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from core.money import format_amount

from .organization import Department, Position, SystemRole


def contract_pdf_path(instance, filename):
    """
    Cesta pro uložení vygenerované pracovní smlouvy (DPP).
    Náhodná přípona brání uhodnutí adresy souboru s osobními údaji.
    """
    year = timezone.now().strftime('%Y')
    number = instance.personal_number or f"ID{instance.id or 'new'}"
    return f"contracts/{year}/{instance.contract_type}_{number}_{secrets.token_hex(8)}.pdf"


def termination_pdf_path(instance, filename):
    """Cesta pro uložení dokumentu o skončení (výpověď / dohoda o ukončení)."""
    year = timezone.now().strftime('%Y')
    number = instance.personal_number or f"ID{instance.id or 'new'}"
    return f"terminations/{year}/{instance.contract_type}_{number}_{secrets.token_hex(8)}.pdf"


def _czech_days(count):
    """Správný tvar slova „den“ podle počtu: 1 den, 2–4 dny, 5 dní."""
    count = abs(count)
    if count == 1:
        return "den"
    if 2 <= count <= 4:
        return "dny"
    return "dní"


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

    EDUCATION_CHOICES = [
        ('A', 'Bez vzdělání'),
        ('B', 'Neúplné základní vzdělání'),
        ('C', 'Základní vzdělání'),
        ('D', 'Nižší střední vzdělání'),
        ('E', 'Nižší střední odborné vzdělání'),
        ('H', 'Střední odborné s výučním listem'),
        ('J', 'Střední bez maturity i výučního listu'),
        ('K', 'Úplné střední všeobecné (gymnázium)'),
        ('L', 'Úplné střední odborné s vyučením i maturitou'),
        ('M', 'Úplné střední odborné s maturitou'),
        ('N', 'Vyšší odborné'),
        ('P', 'Vyšší odborné v konzervatoři'),
        ('R', 'Vysokoškolské bakalářské'),
        ('T', 'Vysokoškolské magisterské'),
        ('V', 'Vysokoškolské doktorské'),
    ]

    TERMINATION_TYPE_CHOICES = [
        ('AGREEMENT', 'Dohoda o ukončení'),
        ('EMPLOYER_NOTICE', 'Výpověď ze strany zaměstnavatele'),
        ('EMPLOYEE_NOTICE', 'Výpověď ze strany zaměstnance'),
        ('OTHER', 'Jiný způsob (bez dokumentu)'),
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

    # Dočasné heslo od manažera se neukládá – po prvním přihlášení se musí změnit
    must_change_password = models.BooleanField(
        default=False,
        verbose_name="Musí si změnit heslo"
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

    # Údaje vyžadované ČSSZ pro registraci zaměstnance (REGZEC)
    birth_surname = models.CharField(max_length=50, blank=True, verbose_name="Rodné příjmení")
    birth_place = models.CharField(max_length=100, blank=True, verbose_name="Místo narození")
    birth_country = models.CharField(max_length=2, default='CZ', verbose_name="Stát narození (kód)")
    citizenship = models.CharField(max_length=2, default='CZ', verbose_name="Státní občanství (kód)")
    education = models.CharField(
        max_length=1,
        choices=EDUCATION_CHOICES,
        blank=True,
        verbose_name="Nejvyšší dosažené vzdělání"
    )

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
    work_location = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Místo výkonu práce"
    )
    work_municipality = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Obec výkonu práce"
    )
    work_municipality_code = models.CharField(
        max_length=6,
        blank=True,
        verbose_name="Kód obce výkonu práce (ZÚJ)"
    )
    contract_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Smlouva sjednána do"
    )

    # Vygenerovaná smlouva (PDF) – stahuje se jen přes chráněný pohled
    contract_pdf = models.FileField(
        upload_to=contract_pdf_path,
        blank=True,
        null=True,
        verbose_name="Smlouva (PDF)"
    )
    contract_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Smlouva vygenerována"
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
    termination_type = models.CharField(
        max_length=20,
        choices=TERMINATION_TYPE_CHOICES,
        blank=True,
        verbose_name="Způsob ukončení"
    )
    termination_notice_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Datum podpisu / doručení výpovědi"
    )

    # Vygenerovaný dokument o skončení (PDF) – stahuje se jen přes chráněný pohled
    termination_pdf = models.FileField(
        upload_to=termination_pdf_path,
        blank=True,
        null=True,
        verbose_name="Dokument o ukončení (PDF)"
    )
    termination_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Dokument o ukončení vygenerován"
    )

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

    @property
    def sex_from_birth_number(self):
        """Pohlaví podle rodného čísla: u žen je k měsíci připočteno 50 (případně 70)."""
        digits = (self.birth_number or '').replace('/', '').strip()
        if len(digits) < 4 or not digits[:4].isdigit():
            return ''
        return 'Ž' if int(digits[2:4]) > 50 else 'M'

    @property
    def cssz_deadline(self):
        """
        Lhůta pro přihlášení zaměstnance na ČSSZ (REGZEC): od 1. 7. 2026 nejpozději
        v den nástupu, ještě před zahájením práce.
        """
        return self.start_employment_date

    @property
    def cssz_status(self):
        """
        Stav hlášení na ČSSZ pro zobrazení v aplikaci.
        state: done (nahlášeno), ok (dost času), warn (3 a méně dní), today (dnes), late (po lhůtě)
        """
        if self.is_reported_cssz:
            when = timezone.localtime(self.reported_cssz_date).strftime('%d.%m.%Y') if self.reported_cssz_date else ''
            return {'state': 'done', 'text': f"Nahlášeno {when}".strip(), 'days': None}

        deadline = self.cssz_deadline
        if not deadline:
            return {'state': 'warn', 'text': "Chybí datum nástupu", 'days': None}

        days = (deadline - timezone.localdate()).days
        if days > 0:
            return {
                'state': 'ok' if days > 3 else 'warn',
                'text': f"Zbývá {days} {_czech_days(days)} (do {deadline:%d.%m.%Y})",
                'days': days,
            }
        if days == 0:
            return {'state': 'today', 'text': "Nahlásit dnes – před nástupem do práce", 'days': 0}
        return {'state': 'late', 'text': f"Po lhůtě {-days} {_czech_days(-days)}", 'days': days}

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
        return f"Záloha {format_amount(self.amount)} Kč – {self.employee.full_name} ({method_str}, {self.created_at.strftime('%d.%m.%Y %H:%M')})"