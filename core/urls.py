from django.urls import path
from . import views
from core.views import billing_views, payroll_views, advance_views, employee_views, tax_views, two_factor_views

urlpatterns = [
    # Veřejné stránky a autentizace
    path('', views.home_view, name='home'),
    path('prihlaseni/', views.login_view, name='login'),
    path('odhlaseni/', views.logout_view, name='logout'),
    path('profil/', views.profile_view, name='user_profile'),

    # Dvoufázové ověření majitele
    path('overeni/', two_factor_views.two_factor_verify_view, name='two_factor_verify'),
    path('overeni/sparovat/', two_factor_views.two_factor_setup_view, name='two_factor_setup'),
    path('overeni/znovu-sparovat/', two_factor_views.two_factor_reset_view, name='two_factor_reset'),
    
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

    # Kmen zaměstnanců
    path('dispecink/zamestnanci/', views.employee_list_view, name='employee_list'),
    path('dispecink/zamestnanec/<int:employee_id>/', views.employee_detail_view, name='employee_detail'),
    path('dispecink/zamestnanci/archiv/', views.employees_archive_list_view, name='employees_archive_list'),
    path('dispecink/zamestnanec/<int:employee_id>/archivovat/', views.archive_employee_view, name='archive_employee'),
    path('dispecink/zamestnanec/<int:employee_id>/heslo/', employee_views.employee_reset_password_view, name='employee_reset_password'),
    path('dispecink/zamestnanec/<int:employee_id>/smlouva/', employee_views.employee_contract_view, name='employee_contract'),
    path('dispecink/zamestnanec/<int:employee_id>/smlouva/vygenerovat/', employee_views.employee_contract_regenerate_view, name='employee_contract_regenerate'),
    path('dispecink/zamestnanec/<int:employee_id>/ukonceni/', employee_views.employee_termination_view, name='employee_termination'),
    path('dispecink/zamestnanec/<int:employee_id>/ukonceni/vygenerovat/', employee_views.employee_termination_regenerate_view, name='employee_termination_regenerate'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/', employee_views.employee_cssz_mark_view, name='employee_cssz_mark'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/xml/', employee_views.employee_cssz_xml_view, name='employee_cssz_xml'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/udaje/', employee_views.employee_cssz_data_view, name='employee_cssz_data'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/odeslat/', employee_views.employee_cssz_send_view, name='employee_cssz_send'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/odpoved/', employee_views.employee_cssz_protocol_check_view, name='employee_cssz_protocol_check'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/protokol/<int:submission_id>/', employee_views.employee_cssz_protocol_view, name='employee_cssz_protocol'),
    path('dispecink/zamestnanec/<int:employee_id>/cssz/odhlaska/', employee_views.employee_cssz_deregister_view, name='employee_cssz_deregister'),

    # Prohlášení poplatníka daně („růžový papír“)
    path('dispecink/zamestnanec/<int:employee_id>/prohlaseni/', tax_views.tax_declaration_edit_view, name='tax_declaration_edit'),
    path('dispecink/zamestnanec/<int:employee_id>/prohlaseni/<int:declaration_id>/pdf/', tax_views.tax_declaration_pdf_view, name='tax_declaration_pdf'),
    path('dispecink/zamestnanec/<int:employee_id>/prohlaseni/<int:declaration_id>/podpis/', tax_views.tax_declaration_sign_view, name='tax_declaration_sign'),
    path('dispecink/zamestnanec/<int:employee_id>/prohlaseni/<int:declaration_id>/odvolat/', tax_views.tax_declaration_withdraw_view, name='tax_declaration_withdraw'),

    # Modul Zálohy a Výdajové doklady (VPD)
    path('dispecink/zalohy/', advance_views.advance_list_view, name='advance_list'),
    path('dispecink/zalohy/nova/', advance_views.advance_create_view, name='advance_create'),
    path('dispecink/zamestnanec/<int:employee_id>/zaloha/', advance_views.advance_create_view, name='employee_advance_create'),
    path('dispecink/zalohy/<int:advance_id>/vpd/', advance_views.advance_download_vpd_view, name='advance_download_vpd'),

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
    path('fakturace/<int:invoice_id>/dokument/', billing_views.invoice_document_view, name='invoice_document'),
    path('fakturace/<int:invoice_id>/upravit/', billing_views.invoice_edit_view, name='invoice_edit'),

    # Správa odběratelů (klientů) a střežených objektů
    path('klienti/', billing_views.client_list_view, name='client_list'),
    path('klienti/novy/', billing_views.client_create_view, name='client_create'),
    path('klienti/<int:client_id>/', billing_views.client_detail_view, name='client_detail'),
    path('klienti/<int:client_id>/upravit/', billing_views.client_update_view, name='client_update'),
    path('objekty/<int:object_id>/upravit/', billing_views.guard_object_update_view, name='guard_object_update'),
]