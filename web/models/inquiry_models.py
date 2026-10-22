from django.db import models


class ServiceInquiry(models.Model):
    SERVICE_PHYSICAL = 'PHYSICAL'
    SERVICE_EVENT = 'EVENT'
    SERVICE_ESCORT = 'ESCORT'          # <--- NOVĚ: Doprovody a osobní ochrana
    SERVICE_PCO = 'PCO'
    SERVICE_PATROL = 'PATROL'
    SERVICE_AUDIT = 'AUDIT'
    
    SERVICE_CHOICES = [
        (SERVICE_PHYSICAL, 'Fyzická ostraha objektu'),
        (SERVICE_ESCORT, 'Osobní doprovody & ozbrojená eskorta cenností'), # <--- NOVĚ
        (SERVICE_EVENT, 'Pořadatelská a eventová služba'),
        (SERVICE_PCO, 'PCO & kamerový dohled'),
        (SERVICE_PATROL, 'Mobilní hlídka & výjezdy'),
        (SERVICE_AUDIT, 'Bezpečnostní audit a poradenství'),
    ]

    service_type = models.CharField("Typ poptávané služby", max_length=30, choices=SERVICE_CHOICES, default=SERVICE_PHYSICAL)
    company_name = models.CharField("Firma / Organizace", max_length=150, blank=True)
    contact_name = models.CharField("Jméno a příjmení", max_length=100)
    phone = models.CharField("Telefonní číslo", max_length=30)
    email = models.EmailField("E-mail")
    
    object_location = models.CharField("Místo / Trasa / Město", max_length=150, blank=True)
    estimated_hours_weekly = models.PositiveIntegerField("Odhad hodin", blank=True, null=True)
    calculated_estimate_czk = models.DecimalField("Orientační kalkulace (Kč)", max_digits=12, decimal_places=2, null=True, blank=True)
    
    message = models.TextField("Specifikace poptávky / Trasa / Detaily", blank=True)
    
    is_processed = models.BooleanField("Zpracováno dispečinkem", default=False)
    created_at = models.DateTimeField("Přijato", auto_now_add=True)

    class Meta:
        verbose_name = "Poptávka z webu"
        verbose_name_plural = "Poptávky z webu"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.contact_name} ({self.get_service_type_display()}) - {self.created_at.strftime('%d.%m.%Y')}"