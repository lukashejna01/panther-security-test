from django.contrib import admin
from .models import (
    Department,
    Position,
    Candidate,
    Employee,
    Client,
    GuardObject,
    ContactPerson,
    Shift,
    ShiftAvailability,
    Supplier,
    Invoice,
    InvoiceItem,
)


# ==========================================
# 1. NÁBOROVÁ PIPELINE & ARCHIV ZÁJEMCŮ
# ==========================================
@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
        'last_name',
        'first_name',
        'status',
        'phone',
        'email',
        'interview_date',
        'is_archived',
        'created_at',
    )
    list_filter = ('status', 'is_archived', 'created_at')
    search_fields = ('last_name', 'first_name', 'phone', 'email', 'rejection_reason')
    list_editable = ('status', 'is_archived')
    date_hierarchy = 'created_at'


# ==========================================
# 2. KMENOVÍ ZAMĚSTNANCI, ODDĚLENÍ & POZICE
# ==========================================
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        'last_name',
        'first_name',
        'system_role',
        'position',
        'contract_type',
        'phone',
        'is_reported_cssz',
        'is_active',
        'is_archived',
    )
    list_filter = (
        'system_role',
        'contract_type',
        'department',
        'position',
        'is_reported_cssz',
        'is_active',
        'is_archived',
    )
    search_fields = (
        'last_name',
        'first_name',
        'birth_number',
        'id_card_number',
        'phone',
        'email',
        'user__username',
    )
    list_editable = ('system_role', 'is_active', 'is_archived')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title',)


# ==========================================
# 3. KLIENTI, OBJEKTY & KONTAKTNÍ OSOBY
# ==========================================
class ContactPersonInline(admin.TabularInline):
    model = ContactPerson
    extra = 1


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'ico', 'contact_person', 'contact_phone', 'contact_email', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'ico', 'dic', 'contact_person', 'contact_phone', 'city')
    list_editable = ('is_active',)
    inlines = [ContactPersonInline]


@admin.register(GuardObject)
class GuardObjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'client',
        'city',
        'hourly_rate_cost',
        'hourly_rate_billing',
        'is_active',
    )
    list_filter = ('client', 'city', 'is_active')
    search_fields = ('name', 'street', 'city', 'client__name', 'emergency_phone')
    list_editable = ('hourly_rate_cost', 'hourly_rate_billing', 'is_active')


@admin.register(ContactPerson)
class ContactPersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'guard_object', 'role_or_title', 'phone', 'email')
    list_filter = ('client', 'guard_object')
    search_fields = ('name', 'role_or_title', 'phone', 'email')


# ==========================================
# 4. PLÁNOVÁNÍ SMĚN & DOSTUPNOST
# ==========================================
@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        'guard_object',
        'employee',
        'required_position',
        'start_time',
        'end_time',
        'status',
        'hourly_rate',
        'approved_by',
    )
    list_filter = ('status', 'guard_object__client', 'guard_object', 'required_position')
    search_fields = ('guard_object__name', 'employee__last_name', 'employee__first_name')
    list_editable = ('status', 'employee')
    date_hierarchy = 'start_time'


@admin.register(ShiftAvailability)
class ShiftAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'status', 'note')
    list_filter = ('status', 'date', 'employee')
    search_fields = ('employee__last_name', 'employee__first_name', 'note')
    date_hierarchy = 'date'


# ==========================================
# 5. FAKTURACE & DODAVATELÉ
# ==========================================
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'ico', 'city', 'phone', 'bank_account', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'ico', 'city', 'contact_person', 'phone')
    list_editable = ('is_active',)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number',
        'invoice_type',
        'get_partner',
        'total_amount',
        'issue_date',
        'due_date',
        'status',
    )
    list_filter = ('invoice_type', 'status', 'issue_date')
    search_fields = (
        'invoice_number',
        'variable_symbol',
        'client__name',
        'supplier__name',
        'supplier_name',
    )
    inlines = [InvoiceItemInline]
    date_hierarchy = 'issue_date'
    list_editable = ('status',)

    def get_partner(self, obj):
        if obj.invoice_type == 'OUTGOING':
            return obj.client.name if obj.client else "—"
        return obj.supplier.name if obj.supplier else (obj.supplier_name or "—")
    get_partner.short_description = "Partner (Klient / Dodavatel)"