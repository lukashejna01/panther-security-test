"""
Formuláře pro evidenci, plánování pohovorů a správu zájemců o práci.
"""

from django import forms
from core.models import Candidate, CandidateStatus


class CandidateCreateForm(forms.ModelForm):
    """
    Zadání nového uchazeče manažerem. 
    Termín pohovoru je zcela volitelný – může zůstat prázdný a doplnit se později.
    """
    class Meta:
        model = Candidate
        fields = ['first_name', 'last_name', 'phone', 'email', 'interview_date', 'interview_note', 'note']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jan'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Novák'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420 777 123 456'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'jan.novak@email.cz'}),
            'interview_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'interview_note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Např. centrála velín / recepce'}),
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Např. doporučení od Petra, zájem o noční na OC Arkády...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['interview_date'].required = False
        self.fields['interview_note'].required = False


class CandidateInterviewScheduleForm(forms.ModelForm):
    """
    Rychlý formulář pro dodatečné naplánování nebo změnu termínu pohovoru zájemce.
    Automaticky může přepnout stav na 'INTERVIEW'.
    """
    class Meta:
        model = Candidate
        fields = ['interview_date', 'interview_note', 'status']
        widgets = {
            'interview_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'interview_note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Místo pohovoru / instrukce'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class CandidateStatusUpdateForm(forms.ModelForm):
    """Změna stavu zájemce a poznámky z pohovoru."""
    class Meta:
        model = Candidate
        fields = ['status', 'note']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class CandidateArchiveForm(forms.Form):
    """Vyřazení zájemce do archivu s uvedením důvodu."""
    rejection_reason = forms.CharField(
        label="Důvod vyřazení / archivace",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Např. nezvedá telefon, nepřišel na pohovor, nevyhovuje...'
        })
    )