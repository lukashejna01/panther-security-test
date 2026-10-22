"""
Evidence náboru a zájemců o zaměstnání v Panther Security.
"""

from django.db import models
from django.contrib.auth.models import User


class CandidateStatus(models.TextChoices):
    NEW = 'NEW', 'Nový zájemce'
    INTERVIEW = 'INTERVIEW', 'Pozván na pohovor'
    APPROVED = 'APPROVED', 'Schválen k nástupu'
    HIRED = 'HIRED', 'Nastoupil (převeden do kmene)'
    REJECTED = 'REJECTED', 'Vyřazen / Zamítnut (Archiv)'


class Candidate(models.Model):
    """Zájemce o práci v náborové pipeline."""
    first_name = models.CharField(max_length=50, verbose_name="Jméno")
    last_name = models.CharField(max_length=50, verbose_name="Příjmení")
    phone = models.CharField(max_length=25, verbose_name="Telefon")
    email = models.EmailField(blank=True, verbose_name="E-mail")

    status = models.CharField(
        max_length=20,
        choices=CandidateStatus.choices,
        default=CandidateStatus.NEW,
        verbose_name="Stav náboru"
    )

    interview_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Termín pohovoru (datum a čas)"
    )
    interview_note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Místo / podrobnosti k pohovoru"
    )

    note = models.TextField(blank=True, verbose_name="Poznámka / Záznam z pohovoru")
    rejection_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Důvod vyřazení do archivu"
    )

    is_archived = models.BooleanField(
        default=False,
        verbose_name="V archivu zájemců"
    )

    # Záznam o tom, jaký uživatel zájemce vytvořil
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_candidates",
        verbose_name="Zadal uživatel"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Vytvořen dne")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Aktualizován")

    class Meta:
        verbose_name = "Zájemce o práci"
        verbose_name_plural = "Zájemci o práci"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.get_status_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def has_interview(self):
        return self.interview_date is not None