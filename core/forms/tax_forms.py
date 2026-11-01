"""
Formuláře pro prohlášení poplatníka daně („růžový papír“) a vyživované děti.
"""

import re

from django import forms

from core.models import TaxDeclaration, TaxDeclarationChild


def _birth_number_digits(value):
    return re.sub(r'\D', '', value or '')


class TaxDeclarationForm(forms.ModelForm):
    """Údaje prohlášení – slevy na dani a druhý poplatník (strana 2, bod c)."""

    class Meta:
        model = TaxDeclaration
        fields = [
            'basic_credit', 'disability', 'ztpp',
            'other_parent', 'other_first_name', 'other_last_name', 'other_birth_number', 'other_address',
            'other_claims', 'other_employed', 'other_employer_name', 'other_employer_address',
        ]
        widgets = {
            'disability': forms.Select(attrs={'class': 'form-control'}),
            'other_parent': forms.Select(attrs={'class': 'form-control'}),
            'other_first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'other_last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'other_birth_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RRMMDD/XXXX'}),
            'other_address': forms.TextInput(attrs={'class': 'form-control'}),
            'other_claims': forms.Select(attrs={'class': 'form-control'}),
            'other_employed': forms.Select(attrs={'class': 'form-control'}),
            'other_employer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'other_employer_address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_other_birth_number(self):
        value = _birth_number_digits(self.cleaned_data.get('other_birth_number'))
        if value and len(value) not in (9, 10):
            raise forms.ValidationError("Rodné číslo musí mít 9 nebo 10 číslic.")
        return value

    def check_other_parent(self, claims_children):
        """Bod c) se vyplňuje jen při uplatnění zvýhodnění na děti (poznámka 6 tiskopisu)."""
        data = self.cleaned_data
        if not claims_children:
            for name in ('other_parent', 'other_first_name', 'other_last_name', 'other_birth_number', 'other_address',
                         'other_claims', 'other_employed', 'other_employer_name', 'other_employer_address'):
                data[name] = ''
            return
        if data.get('other_parent') not in ('ANO', 'NE'):
            self.add_error('other_parent', "Při uplatnění zvýhodnění na děti vyplňte, zda děti vyživuje i jiný poplatník.")
            return
        if data['other_parent'] == 'ANO':
            for name in ('other_first_name', 'other_last_name', 'other_birth_number', 'other_address', 'other_claims', 'other_employed'):
                if not data.get(name):
                    self.add_error(name, "Povinné, když děti vyživuje i jiný poplatník.")
            if data.get('other_employed') == 'ANO':
                for name in ('other_employer_name', 'other_employer_address'):
                    if not data.get(name):
                        self.add_error(name, "Povinné, když je druhý poplatník zaměstnán.")


class TaxDeclarationChildForm(forms.ModelForm):
    class Meta:
        model = TaxDeclarationChild
        fields = ['first_name', 'last_name', 'birth_number', 'claim', 'ztpp', 'adult']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'birth_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RRMMDD/XXXX'}),
            'claim': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_birth_number(self):
        value = _birth_number_digits(self.cleaned_data.get('birth_number'))
        if len(value) not in (9, 10):
            raise forms.ValidationError("Rodné číslo musí mít 9 nebo 10 číslic.")
        return value


# Tiskopis má v tabulce dětí 5 řádků
TaxDeclarationChildFormSet = forms.inlineformset_factory(
    TaxDeclaration, TaxDeclarationChild, form=TaxDeclarationChildForm,
    extra=5, max_num=5, validate_max=True, can_delete=True,
)


class TaxDeclarationSignForm(forms.Form):
    """Zaznamenání podpisu zaměstnance (od kdy prohlášení platí) a volitelně sken."""
    signed_on = forms.DateField(label="Podepsáno dne", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    signed_scan = forms.FileField(
        label="Podepsaný sken (nepovinné)", required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
    )


class TaxDeclarationWithdrawForm(forms.Form):
    withdrawn_on = forms.DateField(label="Odvoláno dne", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
