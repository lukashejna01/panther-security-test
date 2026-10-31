"""
Centrální balíček všech pohledů Panther Security.
"""

from .auth_views import (
    home_view,
    login_view,
    logout_view,
    profile_view,
)
from .candidate_views import (
    candidate_list_view,
    schedule_interview_view,
    archive_candidate_view,
    candidates_archive_list_view,
    candidate_onboard_view,
    download_cssz_onz_view,
)
from .employee_views import (
    employee_list_view,
    employee_detail_view,
    archive_employee_view,
    employees_archive_list_view,
)
from .shift_views import (
    shift_planner_calendar_view,
    employee_calendar_view,
    approve_shift_view,
    shift_detail_view,
    claim_shift_view,
)
from .portal_views import (
    employee_portal_view,
    manager_dashboard_view,
    owner_dashboard_view,
)
from .payroll_views import (
    payroll_summary_view,
    payslip_detail_view,
)
from .billing_views import (
    invoice_list_view,
    invoice_detail_view,
    generate_client_invoice_view,
    upload_incoming_invoice_view,
    client_list_view,
    client_create_view,
    client_update_view,
    client_detail_view,
    guard_object_update_view,
    toggle_invoice_payment_status_view,
)
from .advance_views import (
    advance_list_view,
    advance_create_view,
    advance_download_vpd_view,
)