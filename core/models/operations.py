"""
Správa klientů a střežených stanovišť (objektů) Panther Security.
Obsahuje strukturované adresy, GPS souřadnice, provozní směrnice a ekonomické sazby.
"""

from django.db import models


class Client(models.Model):
    """Zákazník / Odběratel bezpečnostní agentury."""
    name = models.CharField(max_length=200, verbose_name="Název firmy / klienta")
    ico = models.CharField(max_length=20, blank=True, verbose_name="IČO")
    dic = models.CharField(max_length=20, blank=True, verbose_name="DIČ")

    # Strukturovaná sídelní / fakturační adresa
    street = models.CharField(max_length=150, blank=True, verbose_name="Ulice")
    house_number = models.CharField(max_length=30, blank=True, verbose_name="Číslo popisné")
    orientation_number = models.CharField(max_length=30, blank=True, verbose_name="Číslo orientační")
    city = models.CharField(max_length=100, blank=True, verbose_name="Město")
    city_part = models.CharField(max_length=100, blank=True, verbose_name="Městská část / obvod")
    zip_code = models.CharField(max_length=15, blank=True, verbose_name="PSČ")

    # Kontaktní údaje
    contact_person = models.CharField(max_length=150, blank=True, verbose_name="Hlavní kontaktní osoba")
    contact_phone = models.CharField(max_length=30, blank=True, verbose_name="Telefon na kontakt")
    contact_email = models.EmailField(blank=True, verbose_name="E-mail na kontakt")

    is_active = models.BooleanField(default=True, verbose_name="Aktivní klient")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Klient"
        verbose_name_plural = "Klienti"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def formatted_street_line(self):
        """Ulice a čísla: např. 'Varšavská 715/36' nebo jen 'Průmyslová 14'."""
        street_part = self.street or ""
        nums = []
        if self.house_number:
            nums.append(self.house_number)
        if self.orientation_number:
            nums.append(self.orientation_number)
        
        num_str = "/".join(nums)
        if street_part and num_str:
            return f"{street_part} {num_str}".strip()
        elif street_part:
            return street_part
        return num_str

    @property
    def formatted_city_line(self):
        """PSČ, Město a Městská část: např. '120 00 Praha 2' nebo '110 00 Praha 1 - Nové Město'."""
        res = f"{self.zip_code} {self.city}".strip()
        if self.city_part:
            res += f" – {self.city_part}"
        return res


class GuardObject(models.Model):
    """Konkrétní střežené stanoviště nebo budova klienta."""
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="guard_objects",
        verbose_name="Klient"
    )
    name = models.CharField(max_length=200, verbose_name="Název stanoviště / objektu")

    street = models.CharField(max_length=150, verbose_name="Ulice")
    house_number = models.CharField(max_length=30, verbose_name="Číslo popisné / orientační")
    city = models.CharField(max_length=100, verbose_name="Město")
    zip_code = models.CharField(max_length=10, verbose_name="PSČ")

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="GPS Šířka (Lat)")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="GPS Délka (Lon)")
    gps_radius_meters = models.PositiveIntegerField(default=150, verbose_name="Povolený rádius pro check-in (metry)")

    instructions = models.TextField(blank=True, verbose_name="Směrnice a instrukce pro výkon služby")
    emergency_phone = models.CharField(max_length=50, blank=True, verbose_name="Pohotovostní telefon / Velín")

    hourly_rate_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=160.00,
        verbose_name="Výchozí hodinová odměna strážného (Kč/h)"
    )
    hourly_rate_billing = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=260.00,
        verbose_name="Fakturační sazba klientovi (Kč/h)"
    )

    is_active = models.BooleanField(default=True, verbose_name="Aktivní stanoviště")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Střežený objekt"
        verbose_name_plural = "Střežené objekty"
        ordering = ['client', 'name']

    def __str__(self):
        return f"{self.client.name} – {self.name}"

    @property
    def full_address(self):
        return f"{self.street} {self.house_number}, {self.city} {self.zip_code}".strip()


class ContactPerson(models.Model):
    """Kontaktní osoby u klienta nebo konkrétního objektu (např. facility manager, velín, ředitel)."""
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="Přiřazený klient"
    )
    guard_object = models.ForeignKey(
        GuardObject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contacts",
        verbose_name="Konkrétní střežený objekt (volitelné)"
    )
    name = models.CharField(max_length=150, verbose_name="Jméno a příjmení")
    role_or_title = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Pracovní pozice / role (např. Facility manažer, Velín, Účtárna)"
    )
    phone = models.CharField(max_length=30, blank=True, verbose_name="Telefonní číslo")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    notes = models.CharField(max_length=255, blank=True, verbose_name="Poznámka / Dostupnost")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kontaktní osoba"
        verbose_name_plural = "Kontaktní osoby"
        ordering = ['client', 'name']

    def __str__(self):
        role = f" ({self.role_or_title})" if self.role_or_title else ""
        return f"{self.name}{role}"