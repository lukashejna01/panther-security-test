"""
Formuláře pro onboarding zaměstnanců z dokladů totožnosti,
editaci profilů a archivaci ukončených pracovních poměrů.
"""

from django import forms
from core.models import Employee


class IDCardUploadForm(forms.Form):
    """Formulář pro nahrání skenu nebo PDF dokladu totožnosti k analýze přes Claude AI."""
    id_card_image = forms.FileField(
        label="Sken nebo fotografie občanského průkazu / pasu (PDF, JPG, PNG)",
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'})
    )


class EmployeeOnboardingForm(forms.ModelForm):
    """
    Kompletní formulář pro kontrolu vytěžených dat z OP,
    doplnění data nástupu a pojišťovny před vystavením smlouvy a odesláním na ČSSZ.
    """
    class Meta:
        model = Employee
        fields = [
            'first_name',
            'last_name',
            'birth_date',
            'birth_number',
            'id_card_number',
            'street',
            'house_number',
            'orientation_number',
            'city',
            'zip_code',
            'phone',
            'email',
            'bank_account',
            'department',
            'position',
            'contract_type',
            'hourly_rate',
            'start_employment_date',
            'health_insurance_code',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'birth_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RRMMDD/XXXX'}),
            'id_card_number': forms.TextInput(attrs={'class': 'form-control'}),
            'street': forms.TextInput(attrs={'class': 'form-control'}),
            'house_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'č.p.'}),
            'orientation_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'č.o.'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '370 01'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420 777 123 456'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '123456789/0300'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'position': forms.Select(attrs={'class': 'form-control'}),
            'contract_type': forms.Select(attrs={'class': 'form-control'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '1.00'}),
            'start_employment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'health_insurance_code': forms.Select(attrs={'class': 'form-control'}),
        }


class EmployeeProfileUpdateForm(forms.ModelForm):
    """Formulář pro úpravu vlastního kontaktu a čísla účtu přímo zaměstnancem."""
    class Meta:
        model = Employee
        fields = ['phone', 'email', 'bank_account']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420 777 123 456'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'jan.novak@email.cz'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '123456789/0100'}),
        }


class EmployeeArchiveForm(forms.Form):
    """Ukončení pracovního poměru a přesun zaměstnance do archivu."""
    termination_date = forms.DateField(
        label="Datum ukončení pracovního poměru",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    termination_reason = forms.CharField(
        label="Důvod ukončení",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Např. dohoda, výpověď zaměstnancem, hrubé porušení kázně...'
        })
    )