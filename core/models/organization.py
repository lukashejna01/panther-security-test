"""
Organizační struktura společnosti Panther Security.
Obsahuje oddělení, profesní pozice a systémové role pro oprávnění.
"""

from django.db import models


class Department(models.Model):
    """Oddělení firmy (např. Fyzická ostraha, PCO, Detektivní služby, Administrativa)."""
    name = models.CharField(max_length=100, verbose_name="Název oddělení")
    description = models.TextField(blank=True, verbose_name="Popis oddělení")

    class Meta:
        verbose_name = "Oddělení"
        verbose_name_plural = "Oddělení"
        ordering = ['name']

    def __str__(self):
        return self.name


class Position(models.Model):
    """Kvalifikační pozice (např. Strážný, Velitel směny, Psovod, Recepční)."""
    title = models.CharField(max_length=100, verbose_name="Pracovní pozice")

    class Meta:
        verbose_name = "Pracovní pozice"
        verbose_name_plural = "Pracovní pozice"
        ordering = ['title']

    def __str__(self):
        return self.title


class SystemRole(models.TextChoices):
    """Úroveň přístupových práv v aplikaci."""
    STAFF = 'STAFF', 'Řadový zaměstnanec (Strážný / Recepce)'
    MANAGER = 'MANAGER', 'Manažer / Dispečer'
    OWNER = 'OWNER', 'Majitel / Vedení'