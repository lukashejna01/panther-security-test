"""
Formuláře pro správu odběratelů (klientů), jejich střežených stanovišť (objektů)
a kontaktních osob.
"""

from django import forms
from core.models import Client, GuardObject, ContactPerson


class ClientCreateForm(forms.ModelForm):
    """Založení nového odběratele se strukturovanou adresou."""
    class Meta:
        model = Client
        fields = [
            'name',
            'ico',
            'dic',
            'street',
            'house_number',
            'orientation_number',
            'city',
            'city_part',
            'zip_code',
            'contact_person',
            'contact_phone',
            'contact_email',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Název firmy / klienta'}),
            'ico': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '8místné IČO'}),
            'dic': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CZ...'}),
            'street': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ulice'}),
            'house_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Číslo popisné'}),
            'orientation_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Číslo orientační'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Město'}),
            'city_part': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Městská část (např. Praha 2)'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PSČ'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jméno a příjmení'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420 ...'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'faktury@klient.cz'}),
        }


class ClientUpdateForm(forms.ModelForm):
    """Úprava údajů existujícího klienta."""
    class Meta:
        model = Client
        fields = [
            'name',
            'ico',
            'dic',
            'street',
            'house_number',
            'orientation_number',
            'city',
            'city_part',
            'zip_code',
            'contact_person',
            'contact_phone',
            'contact_email',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'ico': forms.TextInput(attrs={'class': 'form-control'}),
            'dic': forms.TextInput(attrs={'class': 'form-control'}),
            'street': forms.TextInput(attrs={'class': 'form-control'}),
            'house_number': forms.TextInput(attrs={'class': 'form-control'}),
            'orientation_number': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'city_part': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class GuardObjectCreateForm(forms.ModelForm):
    """Přidání nového střeženého stanoviště / objektu ke klientovi."""
    class Meta:
        model = GuardObject
        fields = [
            'name',
            'street',
            'house_number',
            'city',
            'zip_code',
            'hourly_rate_cost',
            'hourly_rate_billing',
            'emergency_phone',
            'instructions',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Např. Centrální sklad hala B'}),
            'street': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Průmyslová'}),
            'house_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '145/2'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Praha 10'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '102 00'}),
            'hourly_rate_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '1.00'}),
            'hourly_rate_billing': forms.NumberInput(attrs={'class': 'form-control', 'step': '1.00'}),
            'emergency_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Pohotovost velín'}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Režim vstupu, obchůzky...'}),
        }


class GuardObjectUpdateForm(forms.ModelForm):
    """Úprava údajů existujícího střeženého objektu."""
    class Meta:
        model = GuardObject
        fields = [
            'name',
            'street',
            'house_number',
            'city',
            'zip_code',
            'hourly_rate_cost',
            'hourly_rate_billing',
            'emergency_phone',
            'instructions',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'street': forms.TextInput(attrs={'class': 'form-control'}),
            'house_number': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control'}),
            'hourly_rate_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '1.00'}),
            'hourly_rate_billing': forms.NumberInput(attrs={'class': 'form-control', 'step': '1.00'}),
            'emergency_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ContactPersonForm(forms.ModelForm):
    """Přidání/úprava kontaktní osoby."""
    class Meta:
        model = ContactPerson
        fields = [
            'guard_object',
            'name',
            'role_or_title',
            'phone',
            'email',
            'notes',
        ]
        widgets = {
            'guard_object': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jméno a příjmení'}),
            'role_or_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Např. Vedoucí ostrahy / Velín'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420 ...'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'kontakt@firma.cz'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dostupnost Po-Pá 8-16'}),
        }

    def __init__(self, *args, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        if client:
            self.fields['guard_object'].queryset = client.guard_objects.filter(is_active=True)
            self.fields['guard_object'].empty_label = "— Celá firma (není vázáno na konkrétní objekt) —"