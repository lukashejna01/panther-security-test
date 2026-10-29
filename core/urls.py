from django.urls import path
from . import views
from core.views import billing_views, payroll_views

urlpatterns = [
    # Veřejné stránky a autentizace
    path('', views.home_view, name='home'),
    path('prihlaseni/', views.login_view, name='login'),
    path('odhlaseni/', views.logout_view, name='logout'),
    path('profil/', views.profile_view, name='user_profile'),
    
    # Portály po přihlášení
    path('portal/', views.employee_portal_view, name='employee_portal'),
    path('portal/kalendar/', views.employee_calendar_view, name='employee_calendar'),
    path('dispecink/', views.manager_dashboard_view, name='manager_dashboard'),
    path('dashboard/', views.owner_dashboard_view, name='owner_dashboard'),

    # Plánovač směn a kalendář
    path('dispecink/planovac/', views.shift_planner_calendar_view, name='shift_planner_calendar'),
    path('portal/smena/<int:shift_id>/', views.shift_detail_view, name='shift_detail'),
    path('smena/<int:shift_id>/prevzit/', views.claim_shift_view, name='claim_shift'),
    path('smena/<int:shift_id>/schvalit/', views.approve_shift_view, name='approve_shift'),

    # Nábor & Kandidáti
    path('dispecink/kandidati/', views.candidate_list_view, name='candidate_list'),
    path('dispecink/kandidati/archiv/', views.candidates_archive_list_view, name='candidates_archive_list'),
    path('dispecink/kandidat/<int:candidate_id>/pohovor/', views.schedule_interview_view, name='schedule_interview'),
    path('dispecink/kandidat/<int:candidate_id>/onboard/', views.candidate_onboard_view, name='candidate_onboard'),
    path('dispecink/kandidat/<int:candidate_id>/archivovat/', views.archive_candidate_view, name='archive_candidate'),
    path('dispecink/kandidat/<int:candidate_id>/onz/', views.download_cssz_onz_view, name='download_cssz_onz'),

    # Kmen zaměstnanců
    path('dispecink/zamestnanci/', views.employee_list_view, name='employee_list'),
    path('dispecink/zamestnanec/<int:employee_id>/', views.employee_detail_view, name='employee_detail'),
    path('dispecink/zamestnanci/archiv/', views.employees_archive_list_view, name='employees_archive_list'),
    path('dispecink/zamestnanec/<int:employee_id>/archivovat/', views.archive_employee_view, name='archive_employee'),

    # Výplatní pásky a mzdy
    path('portal/vyplatni-paska/<int:employee_id>/<int:year>/<int:month>/', views.payslip_detail_view, name='payslip_detail'),
    path('dispecink/mzdy/', views.payroll_summary_view, name='payroll_summary'),
    path('dispecink/mzdy/vystavit-pasku/', payroll_views.payslip_custom_generate_view, name='payslip_custom_generate'),

    # Fakturace a správa dokladů
    path('fakturace/', billing_views.invoice_list_view, name='invoice_list'),
    path('faktury/', billing_views.invoice_list_view),
    path('fakturace/prijata/nahrat/', billing_views.upload_incoming_invoice_view, name='invoice_incoming_upload'),
    path('fakturace/vydat/nova/', billing_views.generate_client_invoice_view, name='invoice_generate'),
    path('fakturace/<str:variable_symbol>/', billing_views.invoice_detail_view, name='invoice_detail'),
    path('fakturace/<int:invoice_id>/zaplaceno/', billing_views.toggle_invoice_payment_status_view, name='invoice_toggle_payment'),
    path('fakturace/<int:invoice_id>/smazat/', billing_views.invoice_delete_view, name='invoice_delete'),

    # Správa odběratelů (klientů) a střežených objektů
    path('klienti/', billing_views.client_list_view, name='client_list'),
    path('klienti/novy/', billing_views.client_create_view, name='client_create'),
    path('klienti/<int:client_id>/', billing_views.client_detail_view, name='client_detail'),
    path('klienti/<int:client_id>/upravit/', billing_views.client_update_view, name='client_update'),
    path('objekty/<int:object_id>/upravit/', billing_views.guard_object_update_view, name='guard_object_update'),
]