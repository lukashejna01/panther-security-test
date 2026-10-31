"""
Formuláře pro evidenci a schvalování záloh zaměstnanců Panther Security.
Podpora hotovostního výdeje s digitálním podpisem i bankovního převodu s potvrzením.
"""

from django import forms
from core.models import AdvancePayment, Employee


class AdvancePaymentForm(forms.ModelForm):
    """Formulář pro vystavení nové zálohy manažerem."""
    
    # Skryté pole, kam JavaScript z canvasu propíše Base64 řetězec podpisu
    signature_data = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    class Meta:
        model = AdvancePayment
        fields = [
            'employee',
            'amount',
            'payment_method',
            'bank_confirmation',
            'signature_data',
            'note',
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select select2-enable'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'např. 2000',
                'min': '100',
                'step': '100'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_payment_method'
            }),
            'bank_confirmation': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,image/png,image/jpeg,image/webp'
            }),
            'note': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Volitelná poznámka nebo účel zálohy...'
            }),
        }

    def __init__(self, *args, employee_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Pouze aktivní zaměstnanci seřazení abecedně
        self.fields['employee'].queryset = Employee.objects.filter(
            is_active=True,
            is_archived=False
        ).order_by('last_name', 'first_name')

        # Pokud se formulář otevírá přímo z karty zaměstnance, předvyplníme a zafixujeme ho
        if employee_id:
            self.fields['employee'].initial = employee_id
            self.fields['employee'].widget.attrs['disabled'] = 'disabled'
            self.fields['employee'].required = False

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        signature_data = cleaned_data.get('signature_data')
        bank_confirmation = cleaned_data.get('bank_confirmation')

        if payment_method == 'CASH':
            if not signature_data or signature_data.strip() == "":
                self.add_error('signature_data', 'Pro hotovostní výdej zálohy je vyžadován podpis příjemce na displeji.')
        elif payment_method == 'BANK':
            if not bank_confirmation:
                self.add_error('bank_confirmation', 'Při platbě na účet je povinné nahrát potvrzení o transakci z bankovnictví (PDF nebo obrázek).')

        return cleaned_data