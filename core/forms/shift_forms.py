"""
Formuláře pro plánování směn, dispečink a burzu služeb.
"""

from django import forms
from core.models import Shift


class ShiftCreateForm(forms.ModelForm):
    """Vytvoření nové směny na střeženém stanovišti manažerem."""
    class Meta:
        model = Shift
        fields = [
            'guard_object',
            'required_position',
            'employee',
            'start_time',
            'end_time',
            'hourly_rate',
            'dispatcher_notes',
        ]
        widgets = {
            'guard_object': forms.Select(attrs={'class': 'form-control'}),
            'required_position': forms.Select(attrs={'class': 'form-control'}),
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '1.00'}),
            'dispatcher_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Instrukce: klíče na velínu, střídání ve 22:00, služební vchod...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].required = False
        self.fields['employee'].empty_label = "-- Volná směna (Vypsat na burzu) --"
        self.fields['hourly_rate'].required = False
        self.fields['hourly_rate'].widget.attrs.update({
            'placeholder': 'Ponechte prázdné pro výchozí sazbu stanoviště'
        })