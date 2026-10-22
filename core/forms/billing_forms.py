"""
Formuláře pro fakturaci Panther Security (vydané/přijaté faktury) a dodavatele.
"""

from datetime import timedelta
from django import forms
from django.utils import timezone
from core.models import Invoice, Client, Supplier


class InvoiceUploadForm(forms.Form):
    """Nahrání přijaté faktury od dodavatele k vytěžení přes Claude AI."""
    invoice_file = forms.FileField(
        label="Originální soubor faktury (PDF, JPG, PNG)",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'})
    )


class IncomingInvoiceForm(forms.ModelForm):
    """Formulář pro kontrolu a uložení vytěžené přijaté faktury od dodavatele."""
    class Meta:
        model = Invoice
        fields = [
            'supplier_name', 'supplier_ico', 'supplier_dic', 'supplier_bank_account',
            'invoice_number', 'variable_symbol',
            'amount_without_vat', 'vat_rate', 'vat_amount', 'total_amount',
            'issue_date', 'tax_date', 'due_date',
            'notes', 'document_file'
        ]
        widgets = {
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_ico': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_dic': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_bank_account': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'variable_symbol': forms.TextInput(attrs={'class': 'form-control'}),
            'amount_without_vat': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'vat_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'vat_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'tax_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'document_file': forms.FileInput(attrs={'class': 'form-control'}),
        }


class GenerateClientInvoiceForm(forms.Form):
    """Vystavení vydané faktury klientovi."""
    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(is_active=True),
        label="Odběratel (Klient)",
        empty_label="-- Vyberte klienta --",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    issue_date = forms.DateField(
        label="Datum vystavení",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    tax_date = forms.DateField(
        label="Datum zdanitelného plnění (DUZP)",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    due_date = forms.DateField(
        label="Datum splatnosti",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    notes = forms.CharField(
        label="Text / Popis na faktuře",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'form-control',
            'placeholder': 'Fakturujeme Vám za poskytnuté fyzické střežení objektů za období...'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.now().date()
        if not self.is_bound:
            self.fields['issue_date'].initial = today
            self.fields['tax_date'].initial = today
            self.fields['due_date'].initial = today + timedelta(days=14)


class SupplierForm(forms.ModelForm):
    """Zadání nebo editace dodavatele výstroje, techniky či služeb."""
    class Meta:
        model = Supplier
        fields = [
            'name', 'ico', 'dic', 'street', 'city', 'zip_code',
            'bank_account', 'contact_person', 'phone', 'email', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'např. Výstroj & Ostraha s.r.o.'}),
            'ico': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '8místné IČO'}),
            'dic': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CZ12345678'}),
            'street': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ulice a číslo'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Město'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PSČ'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '123456789/0100'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420 777 ...'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Podmínky, slevy...'}),
        }