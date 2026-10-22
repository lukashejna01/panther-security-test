"""
Evidence docházky, rozpisu směn a časové dostupnosti strážných.
Obsahuje striktní pravidla pro schvalování směn výhradně v minulosti po jejich skončení.
"""

from django.db import models
from django.utils import timezone

from .operations import GuardObject
from .employee import Employee
from .organization import Position


class ShiftStatus(models.TextChoices):
    """Životní cyklus směny."""
    OPEN = 'OPEN', 'Volná směna na burze'
    ASSIGNED = 'ASSIGNED', 'Přiřazená (Naplánovaná)'
    IN_PROGRESS = 'IN_PROGRESS', 'Probíhající služba (Strážný na objektu)'
    COMPLETED = 'COMPLETED', 'Odslouženo (Čeká na schválení manažerem)'
    APPROVED = 'APPROVED', 'Schváleno pro mzdy'
    CANCELLED = 'CANCELLED', 'Zrušená směna'


class Shift(models.Model):
    """Konkrétní plánovaná nebo odsloužená směna na objektu."""
    guard_object = models.ForeignKey(
        GuardObject,
        on_delete=models.CASCADE,
        related_name="shifts",
        verbose_name="Střežený objekt"
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts",
        verbose_name="Přiřazený strážný"
    )
    required_position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Požadovaná pozice"
    )

    start_time = models.DateTimeField(verbose_name="Začátek směny (plán)")
    end_time = models.DateTimeField(verbose_name="Konec směny (plán)")

    status = models.CharField(
        max_length=20,
        choices=ShiftStatus.choices,
        default=ShiftStatus.OPEN,
        verbose_name="Stav směny"
    )

    actual_start_time = models.DateTimeField(null=True, blank=True, verbose_name="Skutečný příchod (Check-in)")
    actual_end_time = models.DateTimeField(null=True, blank=True, verbose_name="Skutečný odchod (Check-out)")

    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Hodinová mzda strážného (Kč/h)"
    )

    guard_notes = models.TextField(blank=True, verbose_name="Záznam ze služby / Hlášení strážného")
    dispatcher_notes = models.TextField(blank=True, verbose_name="Instrukce dispečinku")

    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_shifts",
        verbose_name="Schválil manažer"
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Čas schválení")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Směna"
        verbose_name_plural = "Směny"
        ordering = ['start_time']

    def __str__(self):
        emp_name = self.employee.full_name if self.employee else "VOLNÁ NA BURZE"
        return f"{self.guard_object.name} | {self.start_time.strftime('%d.%m. %H:%M')} – {self.end_time.strftime('%H:%M')} | {emp_name}"

    def save(self, *args, **kwargs):
        if not self.hourly_rate:
            if self.employee and self.employee.hourly_rate:
                self.hourly_rate = self.employee.hourly_rate
            elif self.guard_object:
                self.hourly_rate = self.guard_object.hourly_rate_cost
        super().save(*args, **kwargs)

    @property
    def planned_hours(self):
        """Počet plánovaných hodin směny."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return round(delta.total_seconds() / 3600, 2)
        return 0.0

    @property
    def total_cost(self):
        """Celkový mzdový nárok za směnu."""
        return round(float(self.planned_hours) * float(self.hourly_rate or 0), 2)

    @property
    def can_be_approved(self):
        """
        Pravidlo: Směnu lze schválit POUZE pokud:
        1. Její plánovaný nebo skutečný konec je v minulosti (už skončila).
        2. Má přiřazeného zaměstnance.
        3. Není zrušená a ještě není schválená.
        Nikdy nelze schválit směnu naplánovanou do budoucna!
        """
        now = timezone.now()
        is_ended = (self.actual_end_time and self.actual_end_time <= now) or (self.end_time <= now)
        return bool(
            self.employee
            and is_ended
            and self.status in [ShiftStatus.COMPLETED, ShiftStatus.ASSIGNED, ShiftStatus.IN_PROGRESS]
        )


class ShiftAvailability(models.Model):
    """Časová dostupnost strážného na konkrétní den v měsíci."""
    class Status(models.TextChoices):
        CAN = 'CAN', 'Můžu sloužit'
        CANNOT = 'CANNOT', 'Nemůžu sloužit (Volno)'

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='availabilities',
        verbose_name="Zaměstnanec"
    )
    date = models.DateField(verbose_name="Datum")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CAN,
        verbose_name="Dostupnost"
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Poznámka (např. jen noční / od 14:00)"
    )

    class Meta:
        verbose_name = "Dostupnost strážného"
        verbose_name_plural = "Dostupnosti strážných"
        unique_together = ('employee', 'date')
        ordering = ['date']

    def __str__(self):
        return f"{self.employee.last_name} – {self.date}: {self.get_status_display()}"