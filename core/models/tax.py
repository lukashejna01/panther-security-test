"""
Prohlášení poplatníka daně z příjmů ze závislé činnosti („růžový papír“, MFin 5457)
a vyživované děti, na které zaměstnanec uplatňuje daňové zvýhodnění.
"""

import secrets
from datetime import date

from django.db import models
from django.utils import timezone

from .employee import Employee


def tax_declaration_pdf_path(instance, filename):
    """Vyplněné prohlášení obsahuje rodná čísla – náhodná přípona brání uhodnutí adresy."""
    number = instance.employee.personal_number or f"ID{instance.employee_id}"
    return f"tax_declarations/{instance.year}/{number}_{secrets.token_hex(8)}.pdf"


class TaxDeclaration(models.Model):
    """Prohlášení poplatníka na jedno zdaňovací období (§ 38k zákona o daních z příjmů)."""

    DISABILITY_CHOICES = [
        ('', 'Ne'),
        ('BASIC', 'Invalidita I. nebo II. stupně (základní sleva)'),
        ('EXTENDED', 'Invalidita III. stupně (rozšířená sleva)'),
    ]
    YES_NO = [('', '–'), ('ANO', 'Ano'), ('NE', 'Ne')]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='tax_declarations', verbose_name="Zaměstnanec")
    year = models.PositiveSmallIntegerField(verbose_name="Zdaňovací období")

    # Slevy podle § 35ba odst. 1
    basic_credit = models.BooleanField(default=True, verbose_name="Základní sleva na poplatníka")
    disability = models.CharField(max_length=10, blank=True, choices=DISABILITY_CHOICES, verbose_name="Sleva na invaliditu")
    ztpp = models.BooleanField(default=False, verbose_name="Sleva na držitele průkazu ZTP/P")

    # Strana 2, bod c): vyživuje tytéž děti i jiný poplatník ve společné domácnosti?
    other_parent = models.CharField(max_length=3, blank=True, choices=YES_NO, verbose_name="Děti vyživuje i jiný poplatník")
    other_first_name = models.CharField(max_length=100, blank=True, verbose_name="Jméno druhého poplatníka")
    other_last_name = models.CharField(max_length=100, blank=True, verbose_name="Příjmení druhého poplatníka")
    other_birth_number = models.CharField(max_length=15, blank=True, verbose_name="Rodné číslo druhého poplatníka")
    other_address = models.CharField(max_length=200, blank=True, verbose_name="Adresa druhého poplatníka")
    other_claims = models.CharField(max_length=3, blank=True, choices=YES_NO, verbose_name="Uplatňuje daňové zvýhodnění")
    other_employed = models.CharField(max_length=3, blank=True, choices=YES_NO, verbose_name="Je zaměstnán(a)")
    other_employer_name = models.CharField(max_length=200, blank=True, verbose_name="Název jeho plátce daně")
    other_employer_address = models.CharField(max_length=200, blank=True, verbose_name="Adresa jeho plátce daně")

    # Prohlášení platí až podpisem zaměstnance; odvoláním přestává platit od dalšího měsíce
    signed_on = models.DateField(null=True, blank=True, verbose_name="Podepsáno zaměstnancem dne")
    withdrawn_on = models.DateField(null=True, blank=True, verbose_name="Odvoláno dne")
    pdf = models.FileField(upload_to=tax_declaration_pdf_path, blank=True, null=True, verbose_name="Vyplněný tiskopis (PDF)")
    signed_scan = models.FileField(upload_to=tax_declaration_pdf_path, blank=True, null=True, verbose_name="Podepsaný sken")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prohlášení poplatníka"
        verbose_name_plural = "Prohlášení poplatníka"
        ordering = ['-year', '-created_at']

    def __str__(self):
        return f"Prohlášení {self.year} – {self.employee.full_name}"

    def is_effective_for(self, year, month):
        """
        Platí pro mzdu za daný měsíc? Musí být podepsané nejpozději v tomto měsíci
        a neodvolané před jeho začátkem.
        """
        if year != self.year or not self.signed_on:
            return False
        month_start = date(year, month, 1)
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        if self.signed_on >= next_month:
            return False
        return not (self.withdrawn_on and self.withdrawn_on < month_start)

    @property
    def state(self):
        if self.withdrawn_on:
            return 'withdrawn'
        return 'signed' if self.signed_on else 'draft'

    @classmethod
    def effective_for(cls, employee, year, month):
        for declaration in cls.objects.filter(employee=employee, year=year).prefetch_related('children'):
            if declaration.is_effective_for(year, month):
                return declaration
        return None

    @classmethod
    def current_for(cls, employee, year=None):
        """Poslední neodvolané prohlášení zaměstnance na daný rok (i nepodepsané)."""
        year = year or timezone.localdate().year
        return cls.objects.filter(employee=employee, year=year, withdrawn_on__isnull=True).first()


class TaxDeclarationChild(models.Model):
    """Vyživované dítě v prohlášení (tabulka na straně 1)."""

    CLAIM_CHOICES = [
        ('1', '1. dítě'),
        ('2', '2. dítě'),
        ('3', '3. a další dítě'),
        ('N', 'Neuplatňuji'),
    ]

    declaration = models.ForeignKey(TaxDeclaration, on_delete=models.CASCADE, related_name='children')
    first_name = models.CharField(max_length=100, verbose_name="Jméno")
    last_name = models.CharField(max_length=100, verbose_name="Příjmení")
    birth_number = models.CharField(max_length=15, verbose_name="Rodné číslo")
    claim = models.CharField(max_length=1, choices=CLAIM_CHOICES, verbose_name="Uplatňuji nárok ve výši na")
    ztpp = models.BooleanField(default=False, verbose_name="Dítě je držitelem ZTP/P")
    adult = models.BooleanField(default=False, verbose_name="Zletilé dítě (soustavně se připravuje na povolání)")

    class Meta:
        verbose_name = "Vyživované dítě"
        verbose_name_plural = "Vyživované děti"
        ordering = ['id']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_claim_display()})"
