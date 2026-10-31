"""
Centrální balíček formulářů aplikace core.
"""

from .candidate_forms import (
    CandidateCreateForm,
    CandidateInterviewScheduleForm,
    CandidateStatusUpdateForm,
    CandidateArchiveForm,
)
from .employee_forms import (
    IDCardUploadForm,
    EmployeeOnboardingForm,
    EmployeeProfileUpdateForm,
    EmployeeArchiveForm,
)
from .shift_forms import (
    ShiftCreateForm,
)
from .billing_forms import (
    InvoiceUploadForm,
    IncomingInvoiceForm,
    GenerateClientInvoiceForm,
    SupplierForm,
)
from .operations_forms import (
    ClientCreateForm,
    ClientUpdateForm,
    GuardObjectCreateForm,
    GuardObjectUpdateForm,
    ContactPersonForm,
)
from .advance_forms import (
    AdvancePaymentForm,
)

__all__ = [
    'CandidateCreateForm',
    'CandidateInterviewScheduleForm',
    'CandidateStatusUpdateForm',
    'CandidateArchiveForm',
    'IDCardUploadForm',
    'EmployeeOnboardingForm',
    'EmployeeProfileUpdateForm',
    'EmployeeArchiveForm',
    'ShiftCreateForm',
    'InvoiceUploadForm',
    'IncomingInvoiceForm',
    'GenerateClientInvoiceForm',
    'SupplierForm',
    'ClientCreateForm',
    'ClientUpdateForm',
    'GuardObjectCreateForm',
    'GuardObjectUpdateForm',
    'ContactPersonForm',
    'AdvancePaymentForm',
]