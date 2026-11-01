"""
Formuláře pro onboarding zaměstnanců z dokladů totožnosti,
editaci profilů a archivaci ukončených pracovních poměrů.
"""

import re
from datetime import date

from django import forms
from django.utils import timezone

from core.models import Employee
from core.services.contract_pdf import compute_termination_date
from core.services.cssz import TERMINATION_REASONS


class IDCardUploadForm(forms.Form):
    """Formulář pro nahrání skenu nebo PDF dokladu totožnosti k analýze přes Claude AI."""
    id_card_image = forms.FileField(
        label="Sken nebo fotografie občanského průkazu / pasu (PDF, JPG, PNG)",
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'})
    )


CSSZ_WIDGETS = {
    'birth_surname': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'U vdaných žen často jiné než současné'}),
    'birth_place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Např. Praha'}),
    'birth_country': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 2, 'placeholder': 'CZ'}),
    'citizenship': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 2, 'placeholder': 'CZ'}),
    'education': forms.Select(attrs={'class': 'form-control'}),
    'work_municipality': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Praha'}),
    'work_municipality_code': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 6, 'placeholder': '554782'}),
}


class EmployeeCsszDataForm(forms.ModelForm):
    """Doplnění údajů potřebných pro přihlášku zaměstnance na ČSSZ (REGZEC)."""
    class Meta:
        model = Employee
        fields = [
            'birth_number',
            'birth_date',
            'birth_surname',
            'birth_place',
            'birth_country',
            'citizenship',
            'education',
            'street',
            'house_number',
            'orientation_number',
            'city',
            'zip_code',
            'work_municipality',
            'work_municipality_code',
        ]
        widgets = {
            'birth_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RRMMDD/XXXX'}),
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'street': forms.TextInput(attrs={'class': 'form-control'}),
            'house_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'č.p.'}),
            'orientation_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'č.o.'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12000'}),
            **CSSZ_WIDGETS,
        }

    def clean_birth_country(self):
        return (self.cleaned_data.get('birth_country') or 'CZ').upper()

    def clean_citizenship(self):
        return (self.cleaned_data.get('citizenship') or 'CZ').upper()


def format_periods(periods):
    """Období pojištění [(od, do)] jako text do formuláře – jedno na řádek."""
    return '\n'.join(f"{start:%d.%m.%Y} – {stop:%d.%m.%Y}" for start, stop in periods)


class CsszDeregistrationForm(forms.Form):
    """
    Odhláška zaměstnance z ČSSZ (REGZEC akce 2) včetně podkladů pro úřad práce.
    Kontrolu podmínek ČSSZ dělá check_deregistration_data(); tady jen převod vstupů.
    """
    SEVERANCE_BELONGS_CHOICES = [('', '– neuvádí se –'), ('N', 'Nenáleží'), ('A', 'Náleží')]
    YES_NO_CHOICES = [('', '–'), ('A', 'Ano'), ('N', 'Ne')]
    SEVERANCE_TYPE_CHOICES = [
        ('severance', 'Odstupné podle § 67 odst. 1 ZP'),
        ('replacement', 'Jednorázová náhrada při skončení PP (§ 271ca ZP)'),
    ]

    ikmpsv = forms.CharField(
        label="OIČ (IK MPSV)", max_length=10, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'placeholder': '10 číslic'}),
    )
    job_id = forms.CharField(
        label="ID zaměstnání (ID PPV)", max_length=22, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric'}),
    )
    no_insurance = forms.BooleanField(
        label="Zaměstnání nezaložilo účast na pojištění (např. DPP pod limitem) nebo pobírá starobní důchod",
        required=False,
    )
    reason = forms.ChoiceField(
        label="Důvod ukončení pracovněprávního vztahu", required=False,
        choices=[('', '– vyberte –')] + TERMINATION_REASONS,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    avg_net = forms.IntegerField(
        label="Průměrný měsíční čistý (pravděpodobný) výdělek (Kč)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 1}),
    )
    periods = forms.CharField(
        label="Doby důchodového pojištění za posledních 24 měsíců", required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '01.04.2026 – 31.10.2026'}),
        help_text="Jedno období na řádek ve tvaru 01.04.2026 – 31.10.2026.",
    )
    severance_belongs = forms.ChoiceField(
        label="Odchodné / odstupné", required=False, choices=SEVERANCE_BELONGS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    severance_type = forms.ChoiceField(
        label="Druh", required=False, choices=SEVERANCE_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    severance_amount = forms.IntegerField(
        label="Částka zúčtovaná k výplatě (Kč)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 1}),
    )
    severance_paid_full = forms.ChoiceField(
        label="Vyplaceno v plné výši", required=False, choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    _PERIOD = re.compile(r'^\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*[-–—]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*$')

    def clean_ikmpsv(self):
        return re.sub(r'\D', '', self.cleaned_data.get('ikmpsv') or '')

    def clean_job_id(self):
        return re.sub(r'\D', '', self.cleaned_data.get('job_id') or '')

    def clean_periods(self):
        periods = []
        for line in (self.cleaned_data.get('periods') or '').splitlines():
            if not line.strip():
                continue
            match = self._PERIOD.match(line)
            if not match:
                raise forms.ValidationError(f"Řádek „{line.strip()}“ není ve tvaru 01.04.2026 – 31.10.2026.")
            d1, m1, y1, d2, m2, y2 = (int(x) for x in match.groups())
            try:
                periods.append((date(y1, m1, d1), date(y2, m2, d2)))
            except ValueError:
                raise forms.ValidationError(f"Řádek „{line.strip()}“ obsahuje neexistující datum.")
        return periods


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
            'contract_end_date',
            'work_location',
            'work_municipality',
            'work_municipality_code',
            'health_insurance_code',
            'birth_surname',
            'birth_place',
            'birth_country',
            'citizenship',
            'education',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
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
            'start_employment_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'contract_end_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'work_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Např. Praha – objekty dle rozpisu směn'}),
            'health_insurance_code': forms.Select(attrs={'class': 'form-control'}),
            **CSSZ_WIDGETS,
        }

    def clean(self):
        """U DPP jsou místo výkonu a konec dohody povinné – propisují se do smlouvy."""
        cleaned = super().clean()
        if cleaned.get('contract_type') == 'DPP':
            start = cleaned.get('start_employment_date')
            end = cleaned.get('contract_end_date')
            if not end:
                self.add_error('contract_end_date', "U DPP vyplňte, do kdy je dohoda sjednána.")
            elif start and end < start:
                self.add_error('contract_end_date', "Konec dohody nemůže být dříve než datum nástupu.")
            if not (cleaned.get('work_location') or '').strip():
                self.add_error('work_location', "U DPP vyplňte místo výkonu práce.")
        return cleaned


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
    """
    Ukončení pracovního poměru a přesun zaměstnance do archivu.
    U výpovědi se den skončení dopočítá z výpovědní doby podle typu smlouvy,
    u dohody o ukončení a jiného způsobu se zadává ručně.
    """
    termination_type = forms.ChoiceField(
        label="Způsob ukončení",
        choices=Employee.TERMINATION_TYPE_CHOICES,
        initial='AGREEMENT',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    notice_date = forms.DateField(
        label="Datum podpisu / doručení výpovědi",
        initial=timezone.localdate,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'})
    )
    termination_date = forms.DateField(
        label="Poměr skončí dnem",
        required=False,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'})
    )
    termination_reason = forms.CharField(
        label="Interní poznámka (nepropisuje se do dokumentu)",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Např. odstěhování, nespolehlivost, ukončení zakázky...'
        })
    )

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee

    def clean(self):
        cleaned = super().clean()
        termination_type = cleaned.get('termination_type')
        notice_date = cleaned.get('notice_date')
        contract_type = self.employee.contract_type if self.employee else None

        end = compute_termination_date(contract_type, termination_type, notice_date, cleaned.get('termination_date'))
        if not end:
            self.add_error('termination_date', "Vyplňte den, kterým poměr skončí.")
        elif notice_date and end < notice_date:
            self.add_error('termination_date', "Poměr nemůže skončit dříve, než je datum podpisu.")
        cleaned['termination_date'] = end
        return cleaned